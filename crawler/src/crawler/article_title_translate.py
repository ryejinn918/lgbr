"""Batch-translate foreign news titles to Korean (OpenRouter)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from crawler.paths import crawler_home, repo_root
from crawler.quality_audit import (
    DEFAULT_MODEL,
    OPENROUTER_URL,
    openrouter_api_key,
)

FOREIGN_NEWS_SOURCES = frozenset({"nikkei"})

TITLE_TRANSLATE_SYSTEM = """You translate foreign news headlines into natural Korean.

Rules:
- Translate each title faithfully; minimize paraphrase.
- Keep proper nouns, company names, tickers, and product names as commonly used.
- Do not add commentary, brackets, or explanations.
- Output a single JSON object only (no markdown):
  {"translations":[{"id":"<same id>","title_ko":"<Korean title>"}]}
- Every input id must appear exactly once in translations.
- title_ko must be non-empty Korean (Hangul allowed with Latin proper nouns).
"""

_BATCH_SIZE = 40
DEFAULT_SPAWN_LIMIT = 500
TITLE_TRANSLATE_LOG = "title_translate.log"


def is_foreign_news_source(source: str) -> bool:
    return str(source or "").strip().lower() in FOREIGN_NEWS_SOURCES


def _parse_translations(content: str) -> dict[str, str]:
    raw = content.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("title translate response is not a JSON object")
    items = parsed.get("translations")
    if not isinstance(items, list):
        raise ValueError("translations missing or not a list")
    out: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        tid = str(item.get("id") or "").strip()
        title_ko = str(item.get("title_ko") or "").strip()
        if tid and title_ko:
            out[tid] = title_ko
    return out


def translate_titles_batch(
    items: list[dict[str, str]],
    *,
    model: str = DEFAULT_MODEL,
) -> dict[str, str]:
    """Translate ``[{id, title}, ...]`` → ``{id: title_ko}``."""
    clean: list[dict[str, str]] = []
    for item in items:
        tid = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        if tid and title:
            clean.append({"id": tid, "title": title})
    if not clean:
        return {}

    api_key = openrouter_api_key()
    merged: dict[str, str] = {}
    with httpx.Client(timeout=120.0) as client:
        for i in range(0, len(clean), _BATCH_SIZE):
            chunk = clean[i : i + _BATCH_SIZE]
            body = {
                "model": model,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "provider": {"sort": "throughput"},
                "messages": [
                    {"role": "system", "content": TITLE_TRANSLATE_SYSTEM},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"titles": chunk}, ensure_ascii=False
                        ),
                    },
                ],
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://localhost/lgbr",
                "X-Title": "lgbr-title-translate",
            }
            resp = client.post(OPENROUTER_URL, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            merged.update(_parse_translations(str(content)))
    return merged


def translate_and_store_missing(
    source: str,
    *,
    limit: int = 200,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Fill ``attrs.title_ko`` for rows missing it. Returns progress stats."""
    from crawler import news_articles_store

    if not is_foreign_news_source(source):
        return {"translated": 0, "skipped": True}

    rows = news_articles_store.list_missing_title_ko(source, limit=limit)
    if not rows:
        return {"translated": 0, "pending": 0}

    payload = [
        {"id": str(r["id"]), "title": str(r.get("title") or "")} for r in rows
    ]
    mapping = translate_titles_batch(payload, model=model)
    now = datetime.now(timezone.utc).isoformat()
    translated = 0
    for rid, title_ko in mapping.items():
        news_articles_store.merge_attrs(
            rid,
            {
                "title_ko": title_ko,
                "title_translated_at": now,
            },
        )
        translated += 1
    return {
        "translated": translated,
        "pending": len(rows),
        "missing_after": max(0, len(rows) - translated),
    }


def ensure_title_ko(
    article_id: UUID | str,
    title: str,
    *,
    model: str = DEFAULT_MODEL,
) -> str | None:
    """Translate a single title and store ``attrs.title_ko``. Returns title_ko."""
    from crawler import news_articles_store

    title = (title or "").strip()
    if not title:
        return None
    mapping = translate_titles_batch(
        [{"id": str(article_id), "title": title}],
        model=model,
    )
    title_ko = mapping.get(str(article_id))
    if not title_ko:
        return None
    news_articles_store.merge_attrs(
        article_id,
        {
            "title_ko": title_ko,
            "title_translated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return title_ko


def _lock_path(source: str) -> Path:
    return crawler_home() / f"title_translate-{source}.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_lock_pid(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if not raw.isdigit():
        return None
    return int(raw)


def _write_lock_pid(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{pid}\n", encoding="utf-8")


def _clear_lock_if_owner(path: Path, pid: int) -> None:
    current = _read_lock_pid(path)
    if current == pid:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def spawn_title_translate(
    source: str,
    *,
    limit: int = DEFAULT_SPAWN_LIMIT,
) -> dict[str, Any]:
    """Start a detached title-translate worker (single-flight per source)."""
    source_s = str(source or "").strip().lower()
    if not is_foreign_news_source(source_s):
        return {
            "spawned": False,
            "skipped_busy": False,
            "skipped": True,
            "source": source_s,
        }

    lim = max(1, min(int(limit), 1000))
    lock = _lock_path(source_s)
    existing = _read_lock_pid(lock)
    if existing is not None and _pid_alive(existing):
        return {
            "spawned": False,
            "skipped_busy": True,
            "pid": existing,
            "source": source_s,
        }

    home = crawler_home()
    home.mkdir(parents=True, exist_ok=True)
    log_path = home / TITLE_TRANSLATE_LOG
    log_f = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
    try:
        log_f.write(
            f"\n--- title-translate spawn {datetime.now(timezone.utc).isoformat()} "
            f"source={source_s} limit={lim} ---\n"
        )
        log_f.flush()
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "crawler",
                "title-translate",
                "run",
                "--source",
                source_s,
                "--limit",
                str(lim),
            ],
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=str(repo_root()),
        )
    except Exception:
        log_f.close()
        raise

    _write_lock_pid(lock, proc.pid)
    return {
        "spawned": True,
        "skipped_busy": False,
        "pid": proc.pid,
        "source": source_s,
        "limit": lim,
        "log": str(log_path),
    }


def run_title_translate_worker(
    source: str,
    *,
    limit: int = DEFAULT_SPAWN_LIMIT,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """CLI worker entry: claim lock, translate missing titles, release lock."""
    source_s = str(source or "").strip().lower()
    if not is_foreign_news_source(source_s):
        return {"translated": 0, "skipped": True, "source": source_s}

    lim = max(1, min(int(limit), 1000))
    lock = _lock_path(source_s)
    pid = os.getpid()
    existing = _read_lock_pid(lock)
    if (
        existing is not None
        and existing != pid
        and _pid_alive(existing)
    ):
        return {
            "translated": 0,
            "skipped_busy": True,
            "pid": existing,
            "source": source_s,
        }

    _write_lock_pid(lock, pid)
    try:
        result = translate_and_store_missing(
            source_s, limit=lim, model=model
        )
        result = {
            **result,
            "source": source_s,
            "pid": pid,
        }
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return result
    finally:
        _clear_lock_if_owner(lock, pid)
