"""Doc compress cache: stable prompt_set label is get-or-create."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from consensus.runs_store import DOC_PROMPT_SET_LABEL, ensure_prompt_set


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


def test_doc_prompt_set_label_is_manual_bump_string():
    assert DOC_PROMPT_SET_LABEL.startswith("consensus-doc-")
    assert DOC_PROMPT_SET_LABEL == "consensus-doc-v2"


def test_ensure_prompt_set_reuses_existing_label():
    existing = {"id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
    cur = MagicMock()
    cur.fetchone.return_value = existing
    conn_cm, conn = _patch_connect(cur)

    with patch("consensus.runs_store.connect", return_value=conn_cm):
        a = ensure_prompt_set(label=DOC_PROMPT_SET_LABEL)
        b = ensure_prompt_set(label=DOC_PROMPT_SET_LABEL)

    assert a == existing["id"]
    assert b == existing["id"]
    assert all("SELECT" in (c.args[0] or "") for c in cur.execute.call_args_list)
    assert not any("INSERT" in (c.args[0] or "") for c in cur.execute.call_args_list)
    conn.commit.assert_not_called()


def test_ensure_prompt_set_inserts_when_missing():
    new_id = "11111111-2222-3333-4444-555555555555"
    cur = MagicMock()
    cur.fetchone.side_effect = [None, {"id": new_id}]
    conn_cm, conn = _patch_connect(cur)

    with patch("consensus.runs_store.connect", return_value=conn_cm):
        out = ensure_prompt_set(label=DOC_PROMPT_SET_LABEL)

    assert out == new_id
    sqls = [c.args[0] for c in cur.execute.call_args_list]
    assert any("SELECT" in s for s in sqls)
    assert any("INSERT INTO consensus_prompt_sets" in s for s in sqls)
    assert sum(1 for s in sqls if "INSERT INTO consensus_prompts" in s) == 7
    conn.commit.assert_called_once()
