"""Cross-platform process handling for consensus workers."""

from __future__ import annotations

from unittest.mock import MagicMock

from lgbr_api import consensus_api


def test_consensus_worker_alive_uses_safe_pid_check_on_windows(monkeypatch):
    monkeypatch.setattr(consensus_api, "_pid_alive", lambda pid: pid == 42)
    monkeypatch.setattr(consensus_api.os, "name", "nt")

    assert consensus_api._consensus_worker_alive(42, "run-id") is True
    assert consensus_api._consensus_worker_alive(41, "run-id") is False


def test_spawn_worker_detaches_on_windows(monkeypatch, tmp_path):
    popen = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(consensus_api.subprocess, "Popen", popen)
    monkeypatch.setattr(consensus_api.os, "name", "nt")
    monkeypatch.setattr(consensus_api, "CONSENSUS_LOG", tmp_path / "consensus.log")

    consensus_api._spawn_worker("run-id")

    kwargs = popen.call_args.kwargs
    assert kwargs["stdin"] is consensus_api.subprocess.DEVNULL
    assert kwargs["env"]["PYTHONUTF8"] == "1"
    assert kwargs["creationflags"] & consensus_api.subprocess.DETACHED_PROCESS
    assert "start_new_session" not in kwargs


def test_theme_preflight_rejects_zero_quality_reports(monkeypatch):
    monkeypatch.setattr(
        consensus_api,
        "list_inputs",
        lambda **_: {
            "ok": True,
            "criteria": {
                "period_months": 3,
                "quality_pass_count": 0,
                "usable_file_count": 0,
            },
        },
    )

    result = consensus_api._theme_start_preflight("display")

    assert result is not None
    assert result["status"] == 422
    assert result["can_start"] is True
    assert result["input_preflight"]["quality_pass_count"] == 0


def test_theme_preflight_rejects_restored_missing_files(monkeypatch):
    monkeypatch.setattr(
        consensus_api,
        "list_inputs",
        lambda **_: {
            "ok": True,
            "criteria": {
                "period_months": 3,
                "quality_pass_count": 2,
                "usable_file_count": 0,
            },
        },
    )

    result = consensus_api._theme_start_preflight("macroeconomy")

    assert result is not None
    assert result["status"] == 422
    assert result["input_preflight"]["quality_pass_count"] == 2


def test_theme_preflight_allows_usable_quality_report(monkeypatch):
    monkeypatch.setattr(
        consensus_api,
        "list_inputs",
        lambda **_: {
            "ok": True,
            "criteria": {
                "quality_pass_count": 1,
                "usable_file_count": 1,
            },
        },
    )

    assert consensus_api._theme_start_preflight("petrochemical") is None