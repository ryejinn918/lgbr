#!/usr/bin/env python3
"""Stop open run; for each theme: thesis → auto-continue → full consensus."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "crawler" / "src"))
sys.path.insert(0, str(ROOT / "api" / "src"))

from crawler.db import load_database_env  # noqa: E402


def _req(
    api: str,
    key: str,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None
    headers = {"X-API-Key": key, "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(
        api.rstrip("/") + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            out = json.loads(raw)
        except Exception:
            out = {"ok": False, "message": raw, "status": e.code}
        if "status" not in out:
            out["status"] = e.code
        return out


def _wait_state(
    api: str,
    key: str,
    run_id: str,
    want: set[str],
    *,
    timeout: int,
    interval: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        d = _req(api, key, f"/api/consensus?run_id={run_id}&events=0")
        run = d.get("run") or {}
        st = str(run.get("state") or d.get("state") or "")
        prog = d.get("progress") or run.get("progress") or {}
        msg = d.get("message") or run.get("message")
        line = f"  state={st} stage={prog.get('stage')} msg={msg}"
        if line != last:
            print(line, flush=True)
            last = line
        if st in want:
            return d
        if st == "error":
            return d
        time.sleep(interval)
    raise TimeoutError(f"timeout waiting for {want} on {run_id}")


def _stop_open(api: str, key: str) -> None:
    d = _req(api, key, "/api/consensus/stop", method="POST", body={})
    print(f"stop: ok={d.get('ok')} msg={d.get('message')}", flush=True)
    # brief settle
    time.sleep(2)


def run_theme(
    api: str,
    key: str,
    theme: str,
    *,
    timeout: int,
    interval: float,
) -> str:
    print(f"\n=== START {theme} ===", flush=True)
    started = _req(
        api,
        key,
        "/api/consensus/start",
        method="POST",
        body={"theme": theme, "until": "thesis"},
    )
    if not started.get("ok"):
        raise RuntimeError(f"start {theme}: {started.get('message')}")
    run = started.get("run") or {}
    run_id = str(run.get("id") or "")
    if not run_id:
        raise RuntimeError(f"start {theme}: missing run id: {started}")
    print(f"run_id={run_id}", flush=True)

    d = _wait_state(
        api, key, run_id, {"awaiting"}, timeout=timeout, interval=interval
    )
    run = d.get("run") or {}
    if str(run.get("state")) != "awaiting":
        raise RuntimeError(
            f"{theme} expected awaiting, got {run.get('state')}: {run.get('message')}"
        )
    criteria = run.get("criteria") or {}
    thesis = criteria.get("thesis")
    pillars = criteria.get("pillar_sketch") or []
    cut = criteria.get("cut_logic")
    print(
        f"  axes ready thesis_len={len(str(thesis or ''))} "
        f"pillars={len(pillars)}",
        flush=True,
    )

    cont = _req(
        api,
        key,
        f"/api/consensus/runs/{run_id}/continue",
        method="POST",
        body={
            "thesis": thesis,
            "cut_logic": cut,
            "pillar_sketch": pillars,
        },
    )
    if not cont.get("ok"):
        raise RuntimeError(f"continue {theme}: {cont.get('message')}")
    print("  continued → full consensus", flush=True)

    d = _wait_state(
        api, key, run_id, {"ended"}, timeout=timeout, interval=interval
    )
    run = d.get("run") or {}
    st = str(run.get("state") or "")
    if st != "ended":
        raise RuntimeError(
            f"{theme} failed state={st} msg={run.get('message')}"
        )
    print(f"=== ENDED {theme} ===", flush=True)
    return run_id


def main() -> int:
    load_database_env()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--themes",
        default="ai,datacenter,macroeconomy,physical_ai,automotive,petrochemical",
        help="comma-separated themes",
    )
    p.add_argument(
        "--api",
        default=os.environ.get("LGBR_API_BASE", "http://127.0.0.1:8787"),
    )
    p.add_argument("--timeout", type=int, default=7200)
    p.add_argument("--interval", type=float, default=10.0)
    args = p.parse_args()

    key = (os.environ.get("LGBR_API_KEY") or "").strip()
    if not key:
        print("LGBR_API_KEY is required", file=sys.stderr)
        return 2

    themes = [t.strip() for t in args.themes.split(",") if t.strip()]
    _stop_open(args.api, key)

    results: list[tuple[str, str]] = []
    for theme in themes:
        try:
            rid = run_theme(
                args.api,
                key,
                theme,
                timeout=args.timeout,
                interval=args.interval,
            )
            results.append((theme, rid))
        except Exception as exc:
            print(f"FAIL {theme}: {exc}", file=sys.stderr, flush=True)
            return 1

    print("\nAll done:")
    for theme, rid in results:
        print(f"  {theme}: {rid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
