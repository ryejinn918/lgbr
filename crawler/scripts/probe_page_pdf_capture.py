#!/usr/bin/env python3
"""Probe page.pdf capture quality at different waits (EY empty-print debug)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crawler.paths import crawler_home  # noqa: E402
from crawler.sources.ey_http import fetch_detail_meta  # noqa: E402
from crawler.sources.page_pdf_capture import LazyCaptureBrowser  # noqa: E402

_BODY_JS = """() => {
  const pick = (sel) => {
    const el = document.querySelector(sel);
    return el ? (el.innerText || '').trim() : '';
  };
  const text =
    pick('main') ||
    pick('article') ||
    pick('[role=main]') ||
    (document.body ? (document.body.innerText || '').trim() : '');
  const cookieBtns = Array.from(
    document.querySelectorAll('button, [role=button], a')
  )
    .map((el) => (el.innerText || el.getAttribute('aria-label') || '').trim())
    .filter((t) => /accept|agree|allow all|동의|수락/i.test(t))
    .slice(0, 5);
  return {
    body_len: text.length,
    title: (document.title || '').trim(),
    cookie_labels: cookieBtns,
  };
}"""


def _pdf_text_len(path: Path, *, max_pages: int = 2) -> int:
    if shutil.which("pdftotext") is None or not path.is_file():
        return -1
    proc = subprocess.run(
        ["pdftotext", "-f", "1", "-l", str(max_pages), str(path), "-"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return len((proc.stdout or "").strip())


def _dismiss_cookies(page: Any) -> str | None:
    selectors = [
        "button:has-text('Accept')",
        "button:has-text('Accept all')",
        "button:has-text('Allow all')",
        "button:has-text('Agree')",
        "button:has-text('I agree')",
        "#onetrust-accept-btn-handler",
        ".onetrust-accept-btn-handler",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=800):
                loc.click(timeout=2000)
                return sel
        except Exception:
            continue
    return None


def _snapshot(
    page: Any,
    *,
    out_dir: Path,
    slug: str,
    label: str,
) -> dict[str, Any]:
    detail = page.evaluate(_BODY_JS)
    pdf_path = out_dir / f"{slug}__{label}.pdf"
    png_path = out_dir / f"{slug}__{label}.png"
    page.pdf(path=str(pdf_path), format="A4", print_background=True)
    try:
        page.screenshot(path=str(png_path), full_page=False)
    except Exception as exc:
        png_path = Path(f"screenshot_fail:{exc}")
    return {
        "label": label,
        "body_len": int(detail.get("body_len") or 0),
        "title": detail.get("title"),
        "cookie_labels": detail.get("cookie_labels") or [],
        "pdf_bytes": pdf_path.stat().st_size if pdf_path.is_file() else 0,
        "pdf_text_len": _pdf_text_len(pdf_path),
        "pdf": str(pdf_path),
        "png": str(png_path),
    }


def probe_url(url: str, *, out_dir: Path, slug: str) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_href, pub = fetch_detail_meta(url)
    result: dict[str, Any] = {
        "url": url,
        "slug": slug,
        "http_pdf_url": pdf_href,
        "http_publish_date": pub.isoformat() if pub else None,
        "steps": [],
    }
    capture = LazyCaptureBrowser("ey-probe", headless=True)
    try:
        page = capture.page
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(500)
        result["steps"].append(_snapshot(page, out_dir=out_dir, slug=slug, label="t500ms"))

        page.wait_for_timeout(1500)
        result["steps"].append(_snapshot(page, out_dir=out_dir, slug=slug, label="t2s"))

        clicked = _dismiss_cookies(page)
        page.wait_for_timeout(500)
        step = _snapshot(page, out_dir=out_dir, slug=slug, label="t2s_cookie")
        step["cookie_clicked"] = clicked
        result["steps"].append(step)

        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception as exc:
            result["networkidle_error"] = str(exc)[:200]
        page.wait_for_timeout(500)
        result["steps"].append(
            _snapshot(page, out_dir=out_dir, slug=slug, label="networkidle")
        )
    finally:
        capture.close()
    return result


def _default_urls_from_db() -> list[tuple[str, str]]:
    from crawler.db import connect

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT title, attrs->>'url' AS url, (attrs->>'bytes')::int AS bytes
                FROM reports
                WHERE source = 'ey'
                  AND status = 'downloaded'
                  AND attrs->>'capture' = 'page.pdf'
                  AND attrs->>'url' IS NOT NULL
                ORDER BY (attrs->>'bytes')::int ASC NULLS LAST
                """
            )
            rows = list(cur.fetchall())
    thin = [r for r in rows if (r.get("bytes") or 0) < 20_000]
    fat = [r for r in rows if (r.get("bytes") or 0) >= 200_000]
    picks: list[tuple[str, str]] = []
    for i, r in enumerate(thin[:2]):
        picks.append((f"thin{i+1}", str(r["url"])))
    if fat:
        picks.append(("ok1", str(fat[0]["url"])))
    return picks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        action="append",
        default=[],
        help="URL to probe (repeatable); default: 2 thin + 1 ok from DB",
    )
    parser.add_argument(
        "--out-dir",
        default=str(crawler_home() / "snapshots" / "ey-pagepdf-probe"),
    )
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    if args.url:
        targets = [(f"u{i+1}", u) for i, u in enumerate(args.url)]
    else:
        targets = _default_urls_from_db()
    if not targets:
        print("no URLs to probe", file=sys.stderr)
        return 1

    print(f"out_dir={out_dir}")
    all_results = []
    for slug, url in targets:
        print(f"\n=== {slug} ===\n{url}", flush=True)
        res = probe_url(url, out_dir=out_dir, slug=slug)
        all_results.append(res)
        print(f"http_pdf_url={res.get('http_pdf_url')}")
        for step in res["steps"]:
            print(
                f"  {step['label']:14} body={step['body_len']:6} "
                f"pdf_bytes={step['pdf_bytes']:8} pdf_text={step['pdf_text_len']:6} "
                f"cookie_click={step.get('cookie_clicked')} "
                f"labels={step.get('cookie_labels')}"
            )

    summary_path = out_dir / "probe_summary.json"
    summary_path.write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nwrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
