#!/usr/bin/env python3
"""Sequentially start Nikkei section feed jobs via the local API."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECTIONS = [
    "economy",  # refresh + title_ko for existing
    "news",
    "business",
    "markets",
    "technology",
    "international",
    "sports",
    "society",
]


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _req(method: str, path: str, body: dict | None = None) -> dict:
    base = os.environ.get("LGBR_API_BASE", "http://127.0.0.1:8787").rstrip("/")
    key = (os.environ.get("LGBR_API_KEY") or "").strip()
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            return {"ok": False, "status": exc.code, "message": raw}


def wait_nikkei_idle(*, timeout: float = 900.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = _req("GET", "/api/collection?source=nikkei")
        job = st.get("job") or {}
        state = str(job.get("state") or "")
        if state in ("", "ended", "error") or job.get("ended_at"):
            return st
        if state not in ("starting", "active", "stopping"):
            return st
        time.sleep(2)
    raise TimeoutError("nikkei collection job still open")


def main() -> int:
    _load_env()
    if not (os.environ.get("LGBR_API_KEY") or "").strip():
        print("LGBR_API_KEY missing", file=sys.stderr)
        return 2

    results: list[dict] = []
    for section in SECTIONS:
        print(f"=== feed section={section} ===", flush=True)
        wait_nikkei_idle()
        started = _req(
            "POST",
            "/api/collection/start",
            {
                "source": "nikkei",
                "capability": "feed",
                "section": section,
                "period_months": 3,
            },
        )
        print(json.dumps(started, ensure_ascii=False)[:400], flush=True)
        if not started.get("ok"):
            results.append({"section": section, "start": started})
            continue
        final = wait_nikkei_idle()
        job = final.get("job") or {}
        progress = job.get("progress") or {}
        summary = {
            "section": section,
            "state": job.get("state"),
            "message": job.get("message"),
            "inserted": progress.get("inserted"),
            "updated": progress.get("updated"),
            "title_translate_spawned": progress.get("title_translate_spawned"),
            "title_translate_skipped_busy": progress.get(
                "title_translate_skipped_busy"
            ),
            "listed": progress.get("listed"),
        }
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        results.append(summary)

    print("=== DONE ===", flush=True)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
