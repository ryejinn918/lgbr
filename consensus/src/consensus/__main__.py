"""CLI: consensus run --theme datacenter | --run-id UUID."""

from __future__ import annotations

import argparse
import sys

from consensus.llm import DEFAULT_MODEL
from consensus.worker import main_run, start_theme_run


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="consensus")
    sub = p.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Create and/or execute a consensus run")
    run_p.add_argument("--theme", choices=["datacenter", "ai", "physical_ai"])
    run_p.add_argument("--run-id", help="Existing run UUID (skip create)")
    run_p.add_argument("--question", default=None)
    run_p.add_argument("--model", default=DEFAULT_MODEL)

    args = p.parse_args(argv)
    if args.cmd == "run":
        if args.run_id:
            run_id = args.run_id
        else:
            if not args.theme:
                p.error("--theme is required unless --run-id is set")
            run_id = start_theme_run(
                theme=args.theme, question=args.question, model=args.model
            )
            print(f"created run_id={run_id}", flush=True)
        main_run(run_id)
        return
    p.error("unknown command")


if __name__ == "__main__":
    main(sys.argv[1:])
