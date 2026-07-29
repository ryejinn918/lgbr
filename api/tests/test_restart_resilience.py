"""API restart reconciliation contracts."""

from __future__ import annotations

import asyncio
import importlib
from unittest.mock import MagicMock, patch

from lgbr_api.consensus_api import _recoverable_thesis, request_stop

app_module = importlib.import_module("lgbr_api.app")


def _patch_connect(cur: MagicMock):
    cursor_cm = MagicMock()
    cursor_cm.__enter__.return_value = cur
    cursor_cm.__exit__.return_value = None
    conn = MagicMock()
    conn.cursor.return_value = cursor_cm
    conn_cm = MagicMock()
    conn_cm.__enter__.return_value = conn
    conn_cm.__exit__.return_value = None
    return conn_cm, conn


def _thesis_row(**overrides):
    row = {
        "state": "active",
        "stop_requested_at": None,
        "criteria": {
            "until": "thesis",
            "thesis": "산업 긴장",
            "pillar_sketch": ["축 1", "축 2"],
        },
        "progress": {"stage": "thesis"},
    }
    row.update(overrides)
    return row


def test_dead_worker_thesis_is_recoverable_only_after_complete_cut():
    assert _recoverable_thesis(_thesis_row()) is True
    assert (
        _recoverable_thesis(
            _thesis_row(criteria={"until": "thesis", "thesis": "산업 긴장"})
        )
        is False
    )
    assert _recoverable_thesis(_thesis_row(progress={"stage": "select"})) is False
    assert _recoverable_thesis(_thesis_row(state="stopping")) is False
    assert _recoverable_thesis(_thesis_row(stop_requested_at="now")) is False


def test_lifespan_reconciles_detached_workers_on_startup(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        app_module,
        "mark_all_open_evals_interrupted",
        lambda: calls.append("evals"),
    )
    monkeypatch.setattr(
        app_module,
        "reconcile_stale_crawls",
        lambda: calls.append("crawls"),
    )
    monkeypatch.setattr(
        app_module,
        "reconcile_stale_jobs",
        lambda: calls.append("collection"),
    )
    monkeypatch.setattr(
        app_module,
        "reconcile_stale_runs",
        lambda: calls.append("consensus"),
    )
    monkeypatch.setattr(
        app_module,
        "shutdown_open_crawl",
        lambda **_: calls.append("shutdown"),
    )

    async def run_lifespan() -> None:
        async with app_module.lifespan(None):
            assert calls == ["evals", "crawls", "collection", "consensus"]

    asyncio.run(run_lifespan())
    assert calls[-1] == "shutdown"


def test_stop_request_handles_awaiting_and_active_in_one_update():
    cur = MagicMock()
    cur.fetchone.return_value = {
        "id": "11111111-2222-3333-4444-555555555555",
        "state": "ended",
        "criteria": {},
        "progress": {},
    }
    conn_cm, conn = _patch_connect(cur)

    with patch("lgbr_api.consensus_api.connect", return_value=conn_cm):
        result = request_stop()

    assert result["ok"] is True
    assert result["can_start"] is True
    cur.execute.assert_called_once()
    sql = cur.execute.call_args.args[0]
    assert "WHEN state = 'awaiting' THEN 'ended'" in sql
    assert "WHEN state IN ('active', 'starting') THEN 'stopping'" in sql
    conn.commit.assert_called_once()
