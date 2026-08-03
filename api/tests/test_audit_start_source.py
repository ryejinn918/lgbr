"""Audit start accepts media source filters for API-driven runs."""

from __future__ import annotations

from lgbr_api.audits import start_audit


def test_start_audit_rejects_unknown_source() -> None:
    out = start_audit(source="not-a-source")
    assert out["ok"] is False
    assert out["status"] == 400
    assert "매체" in (out.get("message") or "")


def test_start_audit_accepts_deloitte_source_before_spawn(
    monkeypatch,
) -> None:
    written: list[dict] = []

    monkeypatch.setattr(
        "lgbr_api.audits._read_job",
        lambda: {"state": "idle", "can_start": True},
    )
    monkeypatch.setattr(
        "lgbr_api.audits._write_job", lambda job: written.append(dict(job))
    )
    monkeypatch.setattr(
        "lgbr_api.audits.subprocess.Popen",
        lambda *a, **k: type("P", (), {"pid": 1})(),
    )

    out = start_audit(source="deloitte", force=False, limit=1)
    assert out["ok"] is True
    assert written
    assert written[0]["source"] == "deloitte"
