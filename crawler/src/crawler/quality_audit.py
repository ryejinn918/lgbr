"""Sector-framework quality audit via OpenRouter (async)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from psycopg.types.json import Jsonb

from crawler.db import connect, load_database_env

DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_CHARS = 7000
PDF_PAGES = 5
DEFAULT_CONCURRENCY = 8

_WATERMARK_RE = re.compile(
    r"DB Copyright © FnGuide Inc\.\s*\([^)]*\)\s*",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """You are a research-report quality auditor for sell-side / broker PDFs.

PASS only when BOTH are true:
1) coherent_framework: the note has a consistent analytical frame (structure, mechanism, macro/tech axis) that organizes the whole piece — not fragmented commentary.
2) broad_sector_coverage: the main body analyzes a sector / value chain / competitive landscape / demand structure broadly.

FAIL when any of these dominate:
- single-stock pitch / "beneficiary" sales note as the core
- company earnings / target-price / fair-value equity note (even if it has a house framework)
- industry buzzwords pasted onto a stock call
- Top picks list as the core with thin sector analysis

Stock mentions / Top picks are OK only as appendix or examples when the core is sector-framed analysis.

Respond with a single JSON object only (no markdown):
{
  "pass": boolean,
  "confidence": number,
  "has_coherent_framework": boolean,
  "has_broad_sector_coverage": boolean,
  "scope": "sector" | "company" | "unclear",
  "topic": string,
  "framework_summary": string | null,
  "fail_reasons": string[],
  "pass_signals": string[],
  "rationale": string
}

Language (mandatory):
- Write topic, framework_summary, fail_reasons, pass_signals, and rationale in Korean.
- Do not use Chinese. English is allowed only for proper nouns, tickers, and product names.

Rules:
- pass MUST be true only if has_coherent_framework AND has_broad_sector_coverage AND scope is "sector".
- If scope is "company", pass MUST be false.
- If text is too thin / unreadable / unrelated, set scope "unclear", pass false, confidence low.
"""


@dataclass(frozen=True)
class AuditTarget:
    id: UUID
    source_key: str
    title: str
    file_path: Path
    text: str

    @property
    def text_len(self) -> int:
        return len(self.text)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def openrouter_api_key() -> str:
    load_database_env()
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    return key


def extract_pdf_text(path: Path, *, max_pages: int = PDF_PAGES) -> str:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if shutil.which("pdftotext") is None:
        raise RuntimeError("pdftotext not found (install poppler-utils)")
    proc = subprocess.run(
        [
            "pdftotext",
            "-f",
            "1",
            "-l",
            str(max_pages),
            "-layout",
            str(path),
            "-",
        ],
        capture_output=True,
        check=False,
    )
    raw = proc.stdout.decode("utf-8", errors="replace")
    text = _WATERMARK_RE.sub(" ", raw)
    text = " ".join(text.split())
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "…"
    return text


def normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
    scope = str(raw.get("scope") or "unclear").strip().lower()
    if scope not in {"sector", "company", "unclear"}:
        scope = "unclear"

    has_fw = bool(raw.get("has_coherent_framework"))
    has_broad = bool(raw.get("has_broad_sector_coverage"))
    passed = bool(raw.get("pass"))

    # Hard corrections
    if scope == "company":
        passed = False
    if not (has_fw and has_broad and scope == "sector"):
        passed = False
    if scope == "unclear":
        passed = False

    try:
        confidence = float(raw.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    fail_reasons = raw.get("fail_reasons") or []
    if not isinstance(fail_reasons, list):
        fail_reasons = [str(fail_reasons)]
    pass_signals = raw.get("pass_signals") or []
    if not isinstance(pass_signals, list):
        pass_signals = [str(pass_signals)]

    summary = raw.get("framework_summary")
    if summary is not None:
        summary = str(summary)

    return {
        "pass": passed,
        "confidence": confidence,
        "has_coherent_framework": has_fw,
        "has_broad_sector_coverage": has_broad,
        "scope": scope,
        "topic": str(raw.get("topic") or "")[:500],
        "framework_summary": summary,
        "fail_reasons": [str(x)[:200] for x in fail_reasons][:20],
        "pass_signals": [str(x)[:200] for x in pass_signals][:20],
        "rationale": str(raw.get("rationale") or "")[:2000],
    }


def fetch_targets(
    *,
    force: bool = False,
    limit: int | None = None,
    theme: str | None = None,
    report_id: UUID | str | None = None,
) -> list[dict[str, Any]]:
    where = [
        "status = 'downloaded'",
        "file_path IS NOT NULL",
    ]
    params: list[Any] = []
    if report_id is not None:
        rid = report_id if isinstance(report_id, UUID) else UUID(str(report_id))
        where.append("id = %s")
        params.append(rid)
    else:
        if not force:
            where.append("quality_at IS NULL")
        if theme:
            where.append("attrs->>'theme' = %s")
            params.append(str(theme))
    where_sql = " AND ".join(where)
    sql = f"""
        SELECT id, source_key, title, file_path
        FROM reports
        WHERE {where_sql}
        ORDER BY last_seen_at DESC NULLS LAST, id DESC
    """
    if limit is not None:
        sql += " LIMIT %s"
        params.append(max(1, int(limit)))

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def prepare_targets(
    rows: list[dict[str, Any]],
) -> tuple[list[AuditTarget], list[tuple[UUID, str]]]:
    """Extract text locally; return ready targets + extract failures (id, error)."""
    ready: list[AuditTarget] = []
    failures: list[tuple[UUID, str]] = []
    for row in rows:
        rid = row["id"]
        if not isinstance(rid, UUID):
            rid = UUID(str(rid))
        raw_path = row.get("file_path")
        if not raw_path:
            failures.append((rid, "missing file_path"))
            continue
        path = Path(str(raw_path))
        try:
            text = extract_pdf_text(path)
        except Exception as exc:  # noqa: BLE001 — batch resilience
            failures.append((rid, f"extract: {exc}"))
            continue
        if len(text.strip()) < 80:
            failures.append((rid, "extract: text too short"))
            continue
        ready.append(
            AuditTarget(
                id=rid,
                source_key=str(row.get("source_key") or ""),
                title=str(row.get("title") or ""),
                file_path=path,
                text=text,
            )
        )
    ready.sort(key=lambda t: t.text_len)
    return ready, failures


def save_quality(
    report_id: UUID,
    *,
    result: dict[str, Any],
    model: str,
    error: str | None = None,
) -> None:
    payload = dict(result)
    if error:
        payload["error"] = error
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE reports
                SET quality_pass = %s,
                    quality_confidence = %s,
                    quality_scope = %s,
                    quality_model = %s,
                    quality_at = %s,
                    quality_json = %s
                WHERE id = %s
                """,
                [
                    result.get("pass") if error is None else False,
                    result.get("confidence"),
                    result.get("scope") or ("unclear" if error else None),
                    model,
                    _now(),
                    Jsonb(payload),
                    report_id,
                ],
            )
        conn.commit()


def save_unclear(report_id: UUID, *, model: str, error: str) -> None:
    save_quality(
        report_id,
        result={
            "pass": False,
            "confidence": 0.0,
            "has_coherent_framework": False,
            "has_broad_sector_coverage": False,
            "scope": "unclear",
            "topic": "",
            "framework_summary": None,
            "fail_reasons": ["extract_or_api_error"],
            "pass_signals": [],
            "rationale": error,
        },
        model=model,
        error=error,
    )


async def _classify_one(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    model: str,
    target: AuditTarget,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    body = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "provider": {"sort": "throughput"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"File: {target.file_path.name}\n"
                    f"Title: {target.title}\n"
                    f"rpt_id: {target.source_key}\n\n"
                    f"Report text (extracted from early pages):\n{target.text}"
                ),
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost/lgbr",
        "X-Title": "lgbr-quality-audit",
    }
    async with semaphore:
        resp = await client.post(OPENROUTER_URL, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if isinstance(content, list):
        # Some providers return content parts
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("model response is not a JSON object")
    result = normalize_result(parsed)
    result["_usage"] = data.get("usage") or {}
    result["_model"] = data.get("model") or model
    return result


async def audit_targets(
    targets: list[AuditTarget],
    *,
    model: str = DEFAULT_MODEL,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> dict[str, int]:
    api_key = openrouter_api_key()
    sem = asyncio.Semaphore(max(1, concurrency))
    stats = {"ok": 0, "fail_api": 0, "pass": 0, "reject": 0}
    lock = asyncio.Lock()

    async with httpx.AsyncClient(timeout=120.0) as client:

        async def run_one(target: AuditTarget) -> None:
            try:
                result = await _classify_one(
                    client,
                    api_key=api_key,
                    model=model,
                    target=target,
                    semaphore=sem,
                )
                used_model = str(result.pop("_model", model))
                result.pop("_usage", None)
                # DB write is sync/blocking; offload lightly via to_thread
                await asyncio.to_thread(
                    save_quality, target.id, result=result, model=used_model
                )
                async with lock:
                    stats["ok"] += 1
                    if result.get("pass"):
                        stats["pass"] += 1
                    else:
                        stats["reject"] += 1
                print(
                    f"ok pass={result.get('pass')} scope={result.get('scope')} "
                    f"conf={result.get('confidence')} {target.source_key} "
                    f"{target.title[:60]}"
                )
            except Exception as exc:  # noqa: BLE001
                await asyncio.to_thread(
                    save_unclear, target.id, model=model, error=str(exc)[:500]
                )
                async with lock:
                    stats["fail_api"] += 1
                print(f"err {target.source_key}: {exc}")

        await asyncio.gather(*(run_one(t) for t in targets))

    return stats


async def run_audit(
    *,
    force: bool = False,
    limit: int | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    model: str = DEFAULT_MODEL,
    theme: str | None = None,
    report_id: UUID | str | None = None,
) -> dict[str, int]:
    rows = fetch_targets(
        force=force, limit=limit, theme=theme, report_id=report_id
    )
    print(
        f"candidates={len(rows)} force={force} theme={theme} "
        f"report_id={report_id} concurrency={concurrency}"
    )
    targets, extract_failures = prepare_targets(rows)
    for rid, err in extract_failures:
        save_unclear(rid, model=model, error=err)
        print(f"extract-fail {rid}: {err}")
    print(f"ready={len(targets)} extract_fail={len(extract_failures)}")
    stats = await audit_targets(
        targets, model=model, concurrency=concurrency
    )
    stats["extract_fail"] = len(extract_failures)
    stats["candidates"] = len(rows)
    return stats
