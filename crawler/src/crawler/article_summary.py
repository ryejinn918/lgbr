"""Summarize news article body text with the media SUMMARY_SYSTEM_PROMPT."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from crawler.quality_audit import (
    DEFAULT_MODEL,
    MEDIA_SUMMARY_MAX_CHARS,
    OPENROUTER_URL,
    SUMMARY_SYSTEM_PROMPT,
    apply_source_pass_policy,
    normalize_media_result,
    openrouter_api_key,
)


def summarize_article_text(
    *,
    title: str,
    source: str,
    raw_text: str,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Return normalized media summary dict (summary, short_title, themes, …).

    Raises on API / parse failure so callers can mark_body_failed.
    """
    text = " ".join((raw_text or "").split()).strip()
    if len(text) > MEDIA_SUMMARY_MAX_CHARS:
        text = text[: MEDIA_SUMMARY_MAX_CHARS - 1].rstrip() + "…"
    if not text:
        raise ValueError("empty article text for summary")

    api_key = openrouter_api_key()
    user = (
        f"Title: {title}\n"
        f"Source: {source}\n"
        f"Page count: 1\n\n"
        "Article / report text (extracted from early pages):\n"
        f"{text}"
    )
    body = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "provider": {"sort": "throughput"},
        "messages": [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost/lgbr",
        "X-Title": "lgbr-article-summary",
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(OPENROUTER_URL, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("model response is not a JSON object")
    result = normalize_media_result(parsed)
    result = apply_source_pass_policy(result, source)
    summary = (result.get("summary") or "").strip()
    if not summary:
        raise ValueError("empty summary from model")
    used_model = str(data.get("model") or model)
    result["summary_model"] = used_model
    result["summarized_at"] = datetime.now(timezone.utc).isoformat()
    return result


def summary_attrs(result: dict[str, Any]) -> dict[str, Any]:
    """Attrs fragment to merge onto news_articles.attrs."""
    out: dict[str, Any] = {
        "summarized_at": result.get("summarized_at")
        or datetime.now(timezone.utc).isoformat(),
    }
    short = result.get("short_title")
    if short:
        out["short_title"] = short
    themes = result.get("themes")
    if isinstance(themes, list):
        out["themes"] = themes
    model = result.get("summary_model")
    if model:
        out["summary_model"] = model
    return out
