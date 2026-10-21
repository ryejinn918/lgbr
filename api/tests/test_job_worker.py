"""Durable worker dispatch and retry policy tests."""

from unittest.mock import MagicMock

from lgbr_api import consensus_api, job_worker
from lgbr_api.processes import durable_workers_enabled


def test_durable_worker_flag(monkeypatch):
    monkeypatch.setenv("LGBR_DURABLE_WORKERS", "true")
    assert durable_workers_enabled() is True
    monkeypatch.setenv("LGBR_DURABLE_WORKERS", "0")
    assert durable_workers_enabled() is False


def test_consensus_dispatch_queues_when_durable(monkeypatch):
    spawn = MagicMock()
    monkeypatch.setenv("LGBR_DURABLE_WORKERS", "1")
    monkeypatch.setattr(consensus_api, "_spawn_worker", spawn)

    consensus_api._dispatch_worker("run-id")

    spawn.assert_not_called()


def test_consensus_dispatch_spawns_in_legacy_mode(monkeypatch):
    spawn = MagicMock()
    monkeypatch.delenv("LGBR_DURABLE_WORKERS", raising=False)
    monkeypatch.setattr(consensus_api, "_spawn_worker", spawn)

    consensus_api._dispatch_worker("run-id")

    spawn.assert_called_once_with("run-id")


def test_retry_policy_stops_deterministic_failures():
    assert job_worker._retryable("temporary connection reset") is True
    assert job_worker._retryable("no quality_pass reports in display pool") is False
    assert job_worker._retryable("password authentication failed") is False


def test_worker_commands_use_existing_cli_contracts():
    crawl = job_worker._command("crawl", "crawl-id")
    consensus = job_worker._command("consensus", "run-id")

    assert crawl[-2:] == ["--crawl-id", "crawl-id"]
    assert consensus[-2:] == ["--run-id", "run-id"]