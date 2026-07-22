"""Postgres connection for the monitor API."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

STATE_LABELS = {
    "logging_in": "로그인 시도 중",
    "logged_in": "계정 사용 중",
    "logging_out": "로그아웃 중",
    "ended": "로그아웃됨",
    "error": "오류",
}

END_REASON_LABELS = {
    "manual": "수동 로그아웃",
    "idle": "미사용 종료",
    "ttl": "유지시간 만료",
    "external": "외부 로그인",
    "error": "오류",
    "shutdown": "프로세스 종료",
}


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
