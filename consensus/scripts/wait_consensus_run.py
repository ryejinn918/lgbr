#!/usr/bin/env python3
"""Wait until a consensus run reaches ended/error.

Bare GET /api/consensus becomes idle with run=null once the worker finishes
(by design: current view only shows open runs). Poll with run_id so the
terminal state is still visible:

  GET /api/consensus?run_id=<uuid>&events=0

Usage (repo root, .env loaded):

  python consensus/scripts/wait_consensus_run.py <run_id>
  python consensus/scripts/wait_consensus_run.py <run_id> --timeout 5400
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def _req(api: str, key: str, path: str) -> dict:
    r = urllib.request.Request(
        api.rstrip("/") + path,
        headers={"X-API-Key": key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return json.loads(raw)
        except Exception:
            return {"ok": False, "message": raw, "status": e.code}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run_id", help="consensus run UUID")
    p.add_argument(
        "--api",
        default=os.environ.get("LGBR_API_BASE", "http://127.0.0.1:8787"),
    )
    p.add_argument("--timeout", type=int, default=5400, help="seconds")
    p.add_argument("--interval", type=float, default=8.0, help="poll seconds")
    args = p.parse_args()

    key = os.environ.get("LGBR_API_KEY") or ""
    if not key:
        print("LGBR_API_KEY is required", file=sys.stderr)
        return 2

    deadline = time.time() + args.timeout
    last = None
    while time.time() < deadline:
        # run_id query: returns ended/error rows; bare /api/consensus would go idle.
        d = _req(
            args.api,
            key,
            f"/api/consensus?run_id={args.run_id}&events=0",
        )
        run = d.get("run") or {}
        st = (run.get("state") or d.get("state") or "").strip()
        prog = d.get("progress") or run.get("progress") or {}
        msg = d.get("message") or run.get("message")
        line = (
            f"state={st} stage={prog.get('stage')} "
            f"docs={prog.get('docs_done')}/{prog.get('docs_total')} "
            f"msg={msg}"
        )
        if line != last:
            print(line, flush=True)
            last = line

        if run.get("id") and str(run.get("id")) != args.run_id:
            print(
                f"unexpected run id {run.get('id')!r}",
                file=sys.stderr,
            )
            return 1

        if st in ("ended", "error"):
            print(f"DONE {st} {msg}", flush=True)
            return 0 if st == "ended" else 1

        time.sleep(args.interval)

    print("timeout", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
