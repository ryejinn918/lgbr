"""Structured operational logging for consensus runs (DB + stdout JSON lines)."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from consensus import runs_store

LEVELS = frozenset({"debug", "info", "warn", "error"})


@dataclass
class ConsensusLogger:
    run_id: str

    def emit(
        self,
        *,
        level: str = "info",
        stage: str = "",
        event: str,
        **detail: Any,
    ) -> None:
        level = level if level in LEVELS else "info"
        payload = {
            "run_id": self.run_id,
            "level": level,
            "stage": stage,
            "event": event,
            "detail": detail,
        }
        try:
            print(json.dumps(payload, ensure_ascii=False), flush=True)
        except Exception:
            print(f"consensus_log {self.run_id} {level} {stage} {event}", flush=True)
        try:
            runs_store.append_event(
                self.run_id,
                level=level,
                stage=stage,
                event=event,
                detail=detail,
            )
        except Exception as exc:
            try:
                print(
                    json.dumps(
                        {
                            "run_id": self.run_id,
                            "level": "warn",
                            "stage": "log",
                            "event": "emit_failed",
                            "detail": {"error": str(exc), "orig_event": event},
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                    flush=True,
                )
            except Exception:
                pass

    def set_progress(self, **fields: Any) -> None:
        try:
            runs_store.update_progress(self.run_id, fields)
        except Exception as exc:
            self.emit(
                level="warn",
                stage="log",
                event="progress_failed",
                error=str(exc),
            )

    @contextmanager
    def stage(self, name: str, **detail: Any) -> Iterator[None]:
        self.emit(level="info", stage=name, event="stage_start", **detail)
        self.set_progress(stage=name)
        try:
            yield
        except Exception as exc:
            self.emit(level="error", stage=name, event="error", error=str(exc))
            raise
        else:
            self.emit(level="info", stage=name, event="stage_end", **detail)
