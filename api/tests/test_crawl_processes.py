"""Cross-platform process handling for FnGuide crawl workers."""

from __future__ import annotations

from unittest.mock import MagicMock

from lgbr_api import crawls


def test_pid_alive_uses_shared_safe_helper(monkeypatch):
    monkeypatch.setattr(crawls, "pid_is_alive", lambda pid: pid == 42)

    assert crawls._pid_alive(42) is True
    assert crawls._pid_alive(41) is False


def test_popen_worker_detaches_on_windows(monkeypatch):
    popen = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(crawls.subprocess, "Popen", popen)
    monkeypatch.setattr(crawls.os, "name", "nt")
    log_f = MagicMock()
    env = {"PYTHONUTF8": "1"}

    crawls._popen_worker(["python", "-m", "crawler"], log_f=log_f, env=env)

    kwargs = popen.call_args.kwargs
    assert kwargs["stdin"] is crawls.subprocess.DEVNULL
    assert kwargs["stdout"] is log_f
    assert kwargs["env"] is env
    assert kwargs["creationflags"] & crawls.subprocess.DETACHED_PROCESS
    assert "start_new_session" not in kwargs
