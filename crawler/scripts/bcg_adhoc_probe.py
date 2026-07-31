#!/usr/bin/env python3
"""Probe BCG list surfaces (allowlist discovery). Never bulk-captures articles.

Uses a self-launched Patchright profile by default. Optionally attach to an
open BCG adhoc CDP session (``--cdp``).

Writes ``.crawler/snapshots/bcg-research/findings.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from crawler.browser import launch_context  # noqa: E402
from crawler.paths import browser_profile_dir  # noqa: E402
from crawler.sources.bcg_browser import (  # noqa: E402
    HUB_URL,
    LIST_URL,
    PROFILES,
    accept_cookies_if_visible,
    collect_list_items,
    get_profile,
    is_publication_article_url,
    open_list_url,
    warmup_hub,
)

OUT_DEFAULT = Path(".crawler/snapshots/bcg-research")
PROBE_PROFILE = browser_profile_dir("browser-profile-bcg-probe")


def _probe_url(page, url: str) -> dict[str, Any]:
    open_list_url(page, url)
    items = collect_list_items(page)
    articles = [i for i in items if is_publication_article_url(i.url)]
    return {
        "url": page.url,
        "requested": url,
        "card_count": len(articles),
        "sample": [
            {
                "title": i.title[:60],
                "url": i.url,
                "date": i.published_at.isoformat() if i.published_at else None,
            }
            for i in articles[:6]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_DEFAULT,
        help="Snapshot directory",
    )
    parser.add_argument(
        "--verify-profiles",
        action="store_true",
        help="Only re-check PROFILES.list_urls card counts",
    )
    args = parser.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    findings: dict[str, Any] = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "hub": HUB_URL,
        "publications": LIST_URL,
        "profiles": {},
        "pagination": {
            "load_more_label_on_publications": False,
            "note": "Load More not confirmed; industry/capability pages are static featured cards",
        },
        "rules": [
            "Only collect a[href] matching /publications/{YYYY}/{slug}",
            "Never invent article slugs or PDF CDN paths",
            "Search job may open only PROFILES[*].list_urls",
        ],
    }

    with launch_context(headless=True, user_data_dir=PROBE_PROFILE) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        warmup_hub(page)
        page.screenshot(path=str(out / "hub.png"), full_page=False)

        if args.verify_profiles:
            targets = {
                pid: list(get_profile(pid).list_urls) for pid in sorted(PROFILES)
            }
        else:
            # Full verify of current allowlist (same as profiles).
            targets = {
                pid: list(p.list_urls) for pid, p in sorted(PROFILES.items())
            }

        for pid, urls in targets.items():
            rows = []
            for url in urls:
                try:
                    row = _probe_url(page, url)
                    print(
                        f"{pid:12} cards={row['card_count']:2} {row['url']}",
                        flush=True,
                    )
                except Exception as exc:
                    row = {"requested": url, "error": str(exc), "card_count": 0}
                    print(f"{pid:12} ERROR {url}: {exc}", flush=True)
                rows.append(row)
            findings["profiles"][pid] = rows
            safe = pid.replace("/", "-")
            try:
                page.screenshot(
                    path=str(out / f"profile-{safe}.png"), full_page=False
                )
            except Exception:
                pass

        # Publications pagination signals
        open_list_url(page, LIST_URL)
        page.screenshot(path=str(out / "publications.png"), full_page=True)
        ui = page.evaluate(
            """() => {
              const loadMore = [...document.querySelectorAll('button,a')].some(
                el => /^\\s*Load More\\s*$/i.test((el.innerText||'').trim())
              );
              return { loadMore, url: location.href };
            }"""
        )
        findings["pagination"]["load_more_label_on_publications"] = bool(
            ui.get("loadMore")
        )

    allowlist = {
        pid: [r["requested"] for r in rows if r.get("card_count", 0) >= 1]
        for pid, rows in findings["profiles"].items()
    }
    findings["allowlist"] = allowlist
    findings["finished_at"] = datetime.now().isoformat(timespec="seconds")

    path = out / "findings.json"
    path.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path}", flush=True)
    empty = [k for k, v in allowlist.items() if not v]
    if empty:
        print(f"WARNING empty profiles: {empty}", flush=True)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
