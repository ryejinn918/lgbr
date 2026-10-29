"""Omdia Latest Releases search and PDF download job."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from crawler import collection_jobs_store, reports_store
from crawler.asset_id import DOWNLOADS_ROOT, downloads_dir, make_asset_id
from crawler.browser import launch_context
from crawler.jobs.media_pace import clamp_item_delay_seconds, pace_after_item
from crawler.paths import browser_profile_dir

SOURCE = "omdia"
HOME_URL = "https://omdia.tech.informa.com/"
LATEST_URL = os.environ.get("OMDIA_LATEST_RELEASES_URL", "")


def _source_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _published_at(text: str) -> date | None:
    value = text or ""
    iso_match = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", value)
    if iso_match:
        try:
            return date(
                int(iso_match.group(1)),
                int(iso_match.group(2)),
                int(iso_match.group(3)),
            )
        except ValueError:
            pass

    formats = (
        (
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(20\d{2})\b",
            "%B %d, %Y",
        ),
        (
            r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b",
            "%d %B %Y",
        ),
        (
            r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+(\d{1,2}),\s+(20\d{2})\b",
            "%b %d, %Y",
        ),
        (
            r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*,?\s+(20\d{2})\b",
            "%d %b, %Y",
        ),
        (
            r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b",
            "%B %Y",
        ),
    )
    for pattern, fmt in formats:
        match = re.search(pattern, value, re.I)
        if not match:
            continue
        try:
            return datetime.strptime(match.group(0), fmt).date()
        except ValueError:
            continue
    return None

def _detail_published_at(page: Any, url: str) -> date | None:
    """Read publication metadata from an Omdia article when the list omits it."""
    try:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        values: list[str] = []
        for selector in (
            "time",
            "meta[property=article:published_time]",
            "meta[property=og:published_time]",
            "meta[property=og:updated_time]",
            "meta[name=datePublished]",
            "meta[name=publishdate]",
            "meta[name=publication_date]",
            "meta[name=date]",
            "meta[itemprop=datePublished]",
            "meta[itemprop=dateCreated]",
            "meta[itemprop=dateModified]",
            "meta[name=DC.date]",
            "meta[name=dc.date]",
        ):
            for node in page.locator(selector).all():
                value = node.get_attribute("content") or node.get_attribute("datetime") or node.inner_text()
                if value:
                    values.append(value)
        for node in page.locator("script[type='application/ld+json']").all():
            value = node.inner_text()
            if value:
                values.append(value)
        values.append(page.locator("body").inner_text()[:8000])
        for value in values:
            published = _published_at(value)
            if published:
                return published
    except Exception:
        return None
    return None

def _login_if_needed(page: Any, username: str, password: str) -> Any:
    page.goto(HOME_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2_000)

    def pages() -> list[Any]:
        return list(dict.fromkeys([page, *list(getattr(page.context, "pages", []))]))

    def frames(target: Any) -> list[Any]:
        return [target, *target.frames]

    def has_session() -> bool:
        return any(
            frame.get_by_text("My Omdia", exact=False).count()
            for target in pages()
            for frame in frames(target)
        )

    if "login" not in page.url.lower() and has_session():
        return page

    signin = re.compile(r"sign\s*in|log\s*in|login|my\s+omdia", re.I)
    for target in pages():
        for frame in frames(target):
            link = frame.locator("a, button").filter(has_text=signin)
            if link.count():
                link.first.click()
                page.wait_for_timeout(2_000)
                break
        else:
            continue
        break

    login_page = page
    email = secret = None
    for target in pages():
        for frame in frames(target):
            candidate_email = frame.locator('input[type="text"]').first
            if not candidate_email.count():
                candidate_email = frame.locator('input[type="email"]').first
            candidate_secret = frame.locator('input[type="password"]').first
            if candidate_email.count() and candidate_secret.count():
                login_page, email, secret = target, candidate_email, candidate_secret
                break
        if email is not None:
            break

    if email is None or secret is None:
        raise RuntimeError(
            "Omdia login form was not found; set OMDIA_LATEST_RELEASES_URL "
            "or log in once with the Omdia browser profile"
        )

    email.fill(username)
    secret.fill(password)
    submit = login_page.locator('input[type="submit"], button[type="submit"]').first
    if not submit.count():
        submit = login_page.locator("button, input[type=submit]").filter(has_text=signin).first
    if not submit.count():
        raise RuntimeError("Omdia login submit button was not found")
    submit.click()
    login_page.wait_for_load_state("domcontentloaded")
    login_page.wait_for_timeout(2_000)
    return login_page


def _open_latest_releases(page: Any) -> None:
    if LATEST_URL:
        page.goto(LATEST_URL, wait_until="domcontentloaded")
        return
    # After login Omdia exposes Latest Releases on the authenticated My Omdia page.
    page.goto("https://omdia.tech.informa.com/myhome", wait_until="domcontentloaded")
    page.wait_for_timeout(2_000)
    body = page.locator("body").inner_text().lower()
    if "latest releases" not in body:
        raise RuntimeError("Omdia Latest Releases page was not found; set OMDIA_LATEST_RELEASES_URL")


def _links(page: Any, cutoff: date, *, news: bool = False) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in page.locator("a").all():
        href = anchor.get_attribute("href") or ""
        title = re.sub(r"\s+", " ", anchor.inner_text()).strip()
        if not href or not title:
            continue
        url = href if href.startswith("http") else page.url.rstrip("/") + "/" + href.lstrip("/")
        haystack = f"{title} {url}".lower()
        if any(token in haystack for token in (".xlsx", ".xls", ".csv", "data")):
            continue
        if news:
            if "/pr/" not in url.lower():
                continue
        elif "analysis" not in haystack and ".pdf" not in haystack:
            continue
        if url in seen:
            continue
        seen.add(url)
        try:
            context_parts: list[str] = []
            for level in range(1, 7):
                parent = anchor.locator("xpath=" + "/.." * level)
                context_parts.append(parent.inner_text(timeout=1_000))
            context_text = " ".join(context_parts)
        except Exception:
            context_text = ""
        published = _published_at(f"{title} {url} {context_text}")
        if published and published < cutoff:
            continue
        result.append({"url": url, "title": title[:500], "published_at": published, "news": news})
    return result


def run_omdia_search_job(
    job_id: UUID | str,
    *,
    catalog: str = "latest",
    period_months: int = 6,
    max_pages: int = 20,
    limit: int | None = None,
    item_delay_seconds: float = 2.0,
    download_root: Path | None = None,
) -> dict[str, Any]:
    del catalog, max_pages
    job = collection_jobs_store.claim_job(job_id)
    if str(job.get("source") or "") != SOURCE:
        return collection_jobs_store.end_job(job_id, error=True, message="source must be omdia")
    if str(job.get("capability") or "") != "search":
        return collection_jobs_store.end_job(job_id, error=True, message="expected capability=search")

    username = os.environ.get("OMDIA_USERNAME", "").strip()
    password = os.environ.get("OMDIA_PASSWORD", "")
    if not username or not password:
        return collection_jobs_store.end_job(job_id, error=True, message="OMDIA_USERNAME and OMDIA_PASSWORD are required")

    period_months = max(1, min(int(period_months), 24))
    cutoff = date.today() - timedelta(days=period_months * 31)
    delay = clamp_item_delay_seconds(item_delay_seconds)
    asset_id = make_asset_id(SOURCE)
    download_dir = downloads_dir(asset_id, root=download_root or DOWNLOADS_ROOT)
    download_dir.mkdir(parents=True, exist_ok=True)
    already = reports_store.downloaded_keys(SOURCE)
    listed = downloaded = failed = 0

    try:
        headed = True
        with launch_context(user_data_dir=browser_profile_dir() / SOURCE, headless=headed) as context:
            page = context.pages[0] if context.pages else context.new_page()
            page = _login_if_needed(page, username, password)
            page.goto(HOME_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(2_000)
            items = _links(page, cutoff, news=True)
            _open_latest_releases(page)
            items.extend(_links(page, cutoff))
            for item in items:
                if collection_jobs_store.stop_requested(job_id):
                    break
                listed += 1
                key = _source_key(item["url"])
                if item["published_at"] is None:
                    item["published_at"] = _detail_published_at(page, item["url"])
                attrs = {"provider": "Omdia", "themes": ["display", "appliance"], "source_url": item["url"]}
                reports_store.upsert_listed(
                    source=SOURCE, source_key=key, title=item["title"],
                    published_at=item["published_at"], attrs=attrs,
                )
                if key in already:
                    continue
                try:
                    response = context.request.get(item["url"], timeout=60_000)
                    payload = response.body()
                    pdf_url = item["url"]
                    if not payload.startswith(b"%PDF"):
                        page.goto(item["url"], wait_until="domcontentloaded")
                        page.wait_for_timeout(1_000)
                        pdf_link = page.locator('a[href*=".pdf" i]').first
                        if pdf_link.count():
                            href = pdf_link.get_attribute("href") or ""
                            pdf_url = href if href.startswith("http") else page.url.rstrip("/") + "/" + href.lstrip("/")
                            payload = context.request.get(pdf_url, timeout=60_000).body()
                    path = download_dir / f"{key}.pdf"
                    if not payload.startswith(b"%PDF"):
                        page.goto(item["url"], wait_until="domcontentloaded")
                        page.wait_for_timeout(1_000)
                        page.pdf(path=str(path), format="A4", print_background=True)
                        payload = path.read_bytes()
                    if not payload.startswith(b"%PDF"):
                        raise RuntimeError("download was not a PDF")
                    path.write_bytes(payload)
                    reports_store.mark_downloaded(
                        source=SOURCE, source_key=key, title=item["title"],
                        published_at=item["published_at"], file_path=str(path),
                        file_name=path.name, attrs={**attrs, "pdf_url": pdf_url, "captured_page": not pdf_url.lower().endswith(".pdf")},
                    )
                    downloaded += 1
                except Exception:
                    failed += 1
                pace_after_item(delay)
                if limit is not None and downloaded >= limit:
                    break
        return collection_jobs_store.end_job(
            job_id, error=False,
            message=f"downloaded={downloaded} listed={listed} failed={failed}",
        )
    except Exception as exc:
        return collection_jobs_store.end_job(job_id, error=True, message=str(exc))
