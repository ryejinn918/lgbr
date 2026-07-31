"""Repo-root ``.crawler/`` path helpers (cwd-independent).

All runtime artifacts (browser profiles, downloads, status, snapshots) live under
the repository root ``.crawler/``, not under ``crawler/.crawler`` when the
process cwd is the crawler package directory.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Locate the monorepo root (directory that contains ``crawler/`` and ``api/``)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "crawler").is_dir() and (parent / "api").is_dir():
            return parent
    # Fallback: cwd-relative layout (unusual; prefer repo layout above).
    return Path.cwd()


def crawler_home() -> Path:
    return repo_root() / ".crawler"


def browser_profile_dir(name: str = "browser-profile") -> Path:
    """Chrome persistent profile directory under ``.crawler/``."""
    return crawler_home() / name


def downloads_dir_root() -> Path:
    return crawler_home() / "downloads"


def snapshots_dir() -> Path:
    return crawler_home() / "snapshots"


def status_path() -> Path:
    return crawler_home() / "status.json"


def session_state_path() -> Path:
    return crawler_home() / "session.json"
