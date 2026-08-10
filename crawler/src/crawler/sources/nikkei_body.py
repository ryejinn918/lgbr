"""Nikkei article body fetch via logged-in Patchright session."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from patchright.sync_api import Page

from crawler.browser import launch_context
from crawler.nikkei_login import HUB_URL, is_logged_in, login
from crawler.paths import browser_profile_dir
from crawler.session import LoginPageError
from crawler.sources.nikkei_feed import SOURCE, article_key_from_url, canonical_article_url

BODY_PROFILE = browser_profile_dir("browser-profile-nikkei-body")

_PAYWALL_MARKERS = (
    "この記事は会員限定",
    "会員限定記事です",
    "登録する",
)


@dataclass(frozen=True)
class NikkeiArticleBody:
    source_key: str
    url: str
    body_text: str


def _credentials() -> tuple[str, str]:
    user = (os.environ.get("NIKKEI_USER_ID") or "").strip()
    password = (os.environ.get("NIKKEI_PASSWORD") or "").strip()
    if not user or not password:
        raise RuntimeError(
            "NIKKEI_USER_ID/NIKKEI_PASSWORD required for nikkei fetch_body"
        )
    return user, password


def extract_body_text(page: Page) -> str:
    """Pull article plain text from the active page."""
    data = page.evaluate(
        """() => {
          const root = document.querySelector("article")
            || document.querySelector("main")
            || document.body;
          if (!root) return { text: "", paras: 0 };
          const clone = root.cloneNode(true);
          for (const sel of [
            "nav", "header", "footer", "aside",
            "script", "style", "noscript",
            "[class*='ranking']", "[class*='recommend']",
            "[class*='Related']", "[class*='related']",
            "[class*='comment']", "[class*='Ask']"
          ]) {
            clone.querySelectorAll(sel).forEach((n) => n.remove());
          }
          const paras = [...clone.querySelectorAll("p")]
            .map((p) => (p.innerText || "").trim())
            .filter((t) => t.length > 20);
          const text = paras.length
            ? paras.join("\\n\\n")
            : (clone.innerText || "").trim();
          return { text, paras: paras.length };
        }"""
    )
    text = re.sub(r"\n{3,}", "\n\n", (data or {}).get("text") or "").strip()
    return text


def looks_paywalled(text: str) -> bool:
    head = (text or "")[:400]
    return any(m in head for m in _PAYWALL_MARKERS) and len(text) < 800


class NikkeiBodyBrowser:
    """Short-lived login browser for body fill (separate profile from adhoc)."""

    def __init__(
        self,
        *,
        headless: bool = True,
        profile_dir: Path | None = None,
    ) -> None:
        self.headless = headless
        self.profile_dir = profile_dir or BODY_PROFILE
        self._stack = None
        self._context = None
        self.page: Page | None = None

    def start(self) -> None:
        from contextlib import ExitStack

        user_id, password = _credentials()
        self._stack = ExitStack()
        self._context = self._stack.enter_context(
            launch_context(
                headless=self.headless,
                user_data_dir=self.profile_dir,
            )
        )
        self.page = (
            self._context.pages[0]
            if self._context.pages
            else self._context.new_page()
        )
        assert self.page is not None
        self.page.goto(HUB_URL, wait_until="domcontentloaded", timeout=60_000)
        if not is_logged_in(self.page):
            login(
                self.page,
                user_id=user_id,
                password=password,
                login_url="https://www.nikkei.com/login",
            )
        if not is_logged_in(self.page):
            self.page.goto(HUB_URL, wait_until="domcontentloaded", timeout=60_000)
        if not is_logged_in(self.page):
            raise LoginPageError(
                f"Nikkei body login failed at {self.page.url}",
                detail={"url": self.page.url, "logged_in": False},
            )

    def fetch(self, *, source_key: str | None = None, url: str | None = None) -> NikkeiArticleBody:
        if self.page is None:
            raise RuntimeError("NikkeiBodyBrowser not started")
        key = (source_key or "").strip().upper()
        if not key and url:
            key = article_key_from_url(url) or ""
        if not key:
            raise ValueError("source_key or article url required")
        final_url = (url or "").strip() or canonical_article_url(key)
        self.page.goto(final_url, wait_until="domcontentloaded", timeout=60_000)
        self.page.wait_for_timeout(800)
        body = extract_body_text(self.page)
        if not body:
            raise RuntimeError(f"empty body for {key}")
        if looks_paywalled(body) and not is_logged_in(self.page):
            raise RuntimeError(f"paywalled / logged out for {key}")
        return NikkeiArticleBody(source_key=key, url=final_url, body_text=body)

    def close(self) -> None:
        if self._stack is not None:
            try:
                self._stack.close()
            except Exception:
                pass
        self._stack = None
        self._context = None
        self.page = None

    def __enter__(self) -> NikkeiBodyBrowser:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def fetch_article_safe(
    source_key: str,
    *,
    url: str | None = None,
    browser: NikkeiBodyBrowser,
) -> tuple[NikkeiArticleBody | None, str | None]:
    try:
        return browser.fetch(source_key=source_key, url=url), None
    except Exception as exc:
        return None, str(exc)
