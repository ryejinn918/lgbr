"""Atomic thesis result persistence and awaiting transition."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from consensus.runs_store import complete_thesis


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


def test_complete_thesis_persists_result_and_state_in_one_update():
    cur = MagicMock()
    cur.fetchone.return_value = {"state": "awaiting"}
    conn_cm, conn = _patch_connect(cur)
    criteria = {"until": "thesis", "thesis": "t", "pillar_sketch": ["a", "b"]}
    progress = {"stage": "thesis", "criteria_snapshot": criteria}

    with patch("consensus.runs_store.connect", return_value=conn_cm):
        state = complete_thesis(
            "11111111-2222-3333-4444-555555555555",
            criteria=criteria,
            progress=progress,
            message="awaiting axis review",
        )

    assert state == "awaiting"
    cur.execute.assert_called_once()
    sql = cur.execute.call_args.args[0]
    assert "SET criteria =" in sql
    assert "progress =" in sql
    assert "state = CASE" in sql
    assert "stop_requested_at" in sql
    conn.commit.assert_called_once()


def test_complete_thesis_reports_stop_winner_as_ended():
    cur = MagicMock()
    cur.fetchone.return_value = {"state": "ended"}
    conn_cm, _ = _patch_connect(cur)

    with patch("consensus.runs_store.connect", return_value=conn_cm):
        state = complete_thesis(
            "11111111-2222-3333-4444-555555555555",
            criteria={"thesis": "t", "pillar_sketch": ["a", "b"]},
            progress={"stage": "thesis"},
        )

    assert state == "ended"
