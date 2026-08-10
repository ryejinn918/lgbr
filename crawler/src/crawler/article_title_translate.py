"""Batch-translate foreign news titles to Korean (OpenRouter)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx

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
