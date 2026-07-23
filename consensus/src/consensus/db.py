"""Postgres helpers for consensus (same env pattern as crawler)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


def load_database_env() -> None:
    root = Path(__file__).resolve().parents[3]
    for path in (root / ".env", Path.cwd() / ".env"):
        if path.is_file():
            load_dotenv(path, override=False)
            break


def database_url() -> str:
    load_database_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    with psycopg.connect(database_url(), row_factory=dict_row) as conn:
        yield conn
