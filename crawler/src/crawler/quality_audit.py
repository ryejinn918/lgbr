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
from crawler.report_themes import REPORT_THEMES, THEME_LABEL_KO
from crawler.reports_store import SOURCE_FNGUIDE

DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_CHARS = 7000
PDF_PAGES = 5
DEFAULT_CONCURRENCY = 8
VALID_THEMES = REPORT_THEMES
_THEME_IDS = ", ".join(sorted(VALID_THEMES))
_THEME_LABEL_LINES = "\n".join(
    f"- {tid}: {THEME_LABEL_KO.get(tid, tid)}" for tid in sorted(VALID_THEMES)
)

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
    "short_title": string,
    "framework_summary": string | null,
    "fail_reasons": string[],
    "pass_signals": string[],
    "rationale": string,
    "themes": string[]
}

Language (mandatory):
- Write topic, short_title, framework_summary, fail_reasons, pass_signals, and rationale in Korean.
- Do not use Chinese. English is allowed only for proper nouns, tickers, and product names.
- Those Korean fields are read by humans. Never put rpt_id, UUID, file paths, or hashes in them.

short_title (citation label — always fill, pass or fail):
- Short nickname for footnotes next to the broker name, e.g. "6월 석화 마진".
- About 8–22 characters. Not a sentence. No broker/provider name inside
  (provider is attached separately as [KB, short_title]).
- Prefer series / period / core theme; do not paste the full original title.

themes (content topics — always fill, pass or fail):
- Zero or more ids from this allowlist only: """ + _THEME_IDS + """
- Labels:
""" + _THEME_LABEL_LINES + """
- Order matters: themes[0] is the PRIMARY topic (desk that owns the note).
- Prefer exactly one theme. Add a second only when BOTH are core analytical frames
  of the note (not seasoning, examples, or one paragraph).
- Disambiguation (mandatory):
  - Pure AIDC / power / site / cooling / colo → datacenter (not ai).
  - Model / LLM / AI chip / AI software demand → ai (not datacenter).
  - Growth / inflation / rates / FX / credit / asset allocation as the frame
    → macroeconomy. If AI is only the narrative hook or one sleeve, do NOT add ai.
  - AI industry / AI-capex / AI semiconductors as the frame → ai (or datacenter).
    Do NOT add macroeconomy just because the note mentions rates, GDP, or allocation.
  - Single-sector industry note (auto, chem, …) → that sector only; not macroeconomy.
- Empty array only when truly off-list / unreadable.

Rules:
- pass MUST be true only if has_coherent_framework AND has_broad_sector_coverage AND scope is "sector".
- If scope is "company", pass MUST be false.
- If text is too thin / unreadable / unrelated, set scope "unclear", pass false, confidence low.
"""

# Non-FnGuide media / consulting pieces: summaries for citation, not sell-side gatekeeping.
SUMMARY_SYSTEM_PROMPT = """You summarize business / management / consulting articles for a research desk.

This is NOT a sell-side equity note. Do NOT judge "sector research pass/fail",
stock pitches, target prices, or broker-note format. Ignore those criteria entirely.

Your job is citation metadata + a faithful Korean summary of the piece's core argument.

Respond with a single JSON object only (no markdown):
{
    "pass": true,
    "confidence": number,
    "has_coherent_framework": boolean,
    "has_broad_sector_coverage": boolean,
    "scope": "sector" | "company" | "unclear",
    "topic": string,
    "short_title": string,
    "framework_summary": string,
    "fail_reasons": [],
    "pass_signals": string[],
    "rationale": string,
    "themes": string[]
}

Field meanings (mandatory):
- pass: always true when the text is readable. Only false if text is empty/unreadable.
- has_coherent_framework: true if the piece has a clear thesis or structured argument.
- has_broad_sector_coverage: true only if it analyzes an industry / market / value chain
  broadly. Leadership, HR, culture, personal productivity → usually false (that is OK).
- scope:
  - "sector" = industry / market / competitive landscape as the core
  - "company" = one firm case study as the core
  - "unclear" = general management, leadership, org behavior, methods (not a defect)
- topic: one short Korean phrase for the subject.
- framework_summary: 2–4 Korean sentences stating the core claim and how it is framed.
  This is the main deliverable. Do not write pass/fail commentary.
- rationale: one Korean sentence on who/what the piece is useful for
  (e.g. "조직 리더의 AI 도입 의사결정에 참고"). Never say it fails broker-report criteria.
- pass_signals: short Korean bullets of useful takeaways (0–3).
- fail_reasons: always [] unless unreadable.

Language (mandatory):
- Write topic, short_title, framework_summary, pass_signals, and rationale in Korean.
- Do not use Chinese. English only for proper nouns / product names.
- Never put UUIDs, file paths, or hashes in human-facing fields.

short_title (citation label — always fill):
- About 8–22 characters. Nickname, not a full sentence.
- No publisher name (HBR, PwC, …) inside.
- Prefer the core theme; do not paste the full original title.

themes (optional content tags):
- Zero or more ids from this allowlist only: """ + _THEME_IDS + """
- Labels:
""" + _THEME_LABEL_LINES + """
- Prefer exactly one when a desk theme clearly owns the piece; else [].
- Empty array is normal for pure management / leadership / HR pieces.
- Disambiguation:
  - Pure AIDC / power / cooling / colo → datacenter (not ai).
  - Model / LLM / AI chip / AI software demand → ai.
  - Macro frame (growth, rates, FX, allocation) → macroeconomy.
  - Single industry note → that sector only.
"""


def system_prompt_for_source(source: str) -> str:
    """FnGuide keeps sell-side gatekeeping; other sources get summary prompts."""
    if str(source or "").strip().lower() == SOURCE_FNGUIDE:
        return SYSTEM_PROMPT
    return SUMMARY_SYSTEM_PROMPT


@dataclass(frozen=True)
class AuditTarget:
    id: UUID
    source: str
    source_key: str
    title: str
    file_path: Path
    text: str

    @property
    def text_len(self) -> int:
        return len(self.text)


def apply_source_pass_policy(
    result: dict[str, Any], source: str
) -> dict[str, Any]:
    """Non-FnGuide sources always pass; keep summary / short_title fields."""
    if str(source or "").strip().lower() == SOURCE_FNGUIDE:
        return result
    out = dict(result)
    out["pass"] = True
    return out


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

    short_title = " ".join(str(raw.get("short_title") or "").split())
    if len(short_title) > 28:
        short_title = short_title[:27].rstrip() + "…"

    themes_raw = raw.get("themes")
    themes: list[str] = []
    if isinstance(themes_raw, list):
        for item in themes_raw:
            s = str(item).strip()
            if s in VALID_THEMES:
                themes.append(s)
    elif isinstance(themes_raw, str) and themes_raw.strip() in VALID_THEMES:
        themes = [themes_raw.strip()]

    return {
        "pass": passed,
        "confidence": confidence,
        "has_coherent_framework": has_fw,
        "has_broad_sector_coverage": has_broad,
        "scope": scope,
        "topic": str(raw.get("topic") or "")[:500],
        "short_title": short_title,
        "framework_summary": summary,
        "fail_reasons": [str(x)[:200] for x in fail_reasons][:20],
        "pass_signals": [str(x)[:200] for x in pass_signals][:20],
        "rationale": str(raw.get("rationale") or "")[:2000],
        "themes": themes,
    }


# Hangul syllable block; absence ≈ English / Latin-only audit text.
_NON_KOREAN_SUMMARY_SQL = """(
  (
    coalesce(quality_json->>'framework_summary', '') <> ''
    AND quality_json->>'framework_summary' !~ '[가-힣]'
  )
  OR (
    coalesce(quality_json->>'topic', '') <> ''
    AND quality_json->>'topic' !~ '[가-힣]'
  )
  OR (
    coalesce(quality_json->>'rationale', '') <> ''
    AND quality_json->>'rationale' !~ '[가-힣]'
  )
)"""


def fetch_targets(
    *,
    force: bool = False,
    limit: int | None = None,
    theme: str | None = None,
    source: str | None = None,
    report_id: UUID | str | None = None,
    non_korean_summary: bool = False,
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
        if source:
            where.append("source = %s")
            params.append(str(source).strip().lower())
        if non_korean_summary:
            where.append("quality_at IS NOT NULL")
            where.append(_NON_KOREAN_SUMMARY_SQL)
        elif not force:
            where.append("quality_at IS NULL")
        if theme:
            if str(theme) == "other":
                valid = sorted(REPORT_THEMES)
                where.append(
                    "("
                    "NOT ("
                    "COALESCE(attrs->'themes', '[]'::jsonb) ?| %s::text[]"
                    " OR ("
                    "  (NOT (attrs ? 'themes')"
                    "   OR jsonb_typeof(attrs->'themes') <> 'array'"
                    "   OR jsonb_array_length(attrs->'themes') = 0)"
                    "  AND ("
                    "    COALESCE(attrs->>'theme', '') = ANY(%s)"
                    "    OR COALESCE(attrs->>'crawl_profile', '') = ANY(%s)"
                    "  )"
                    ")"
                    ")"
                    ")"
                )
                params.extend([valid, valid, valid])
            else:
                where.append(
                    "("
                    "attrs->'themes' ? %s"
                    " OR ("
                    "  (NOT (attrs ? 'themes')"
                    "   OR jsonb_typeof(attrs->'themes') <> 'array'"
                    "   OR jsonb_array_length(attrs->'themes') = 0)"
                    "  AND ("
                    "    attrs->>'theme' = %s"
                    "    OR attrs->>'crawl_profile' = %s"
                    "  )"
                    ")"
                    ")"
                )
                params.extend([str(theme), str(theme), str(theme)])
    where_sql = " AND ".join(where)
    sql = f"""
        SELECT id, source, source_key, title, file_path
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
                source=str(row.get("source") or ""),
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
    themes = result.get("themes")
    if not isinstance(themes, list):
        themes = []
    themes = [str(t) for t in themes if str(t) in VALID_THEMES]
    with connect() as conn:
        with conn.cursor() as cur:
            if error is None:
                cur.execute(
                    """
                    UPDATE reports
                    SET quality_pass = %s,
                        quality_confidence = %s,
                        quality_scope = %s,
                        quality_model = %s,
                        quality_at = %s,
                        quality_json = %s,
                        attrs = COALESCE(attrs, '{}'::jsonb)
                            || jsonb_build_object('themes', %s::jsonb)
                    WHERE id = %s
                    """,
                    [
                        result.get("pass"),
                        result.get("confidence"),
                        result.get("scope"),
                        model,
                        _now(),
                        Jsonb(payload),
                        Jsonb(themes),
                        report_id,
                    ],
                )
            else:
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
                        False,
                        result.get("confidence"),
                        result.get("scope") or "unclear",
                        model,
                        _now(),
                        Jsonb(payload),
                        report_id,
                    ],
                )
        conn.commit()


def save_unclear(report_id: UUID, *, model: str, error: str) -> None:
    # Human-facing rationale stays short Korean; raw error goes to error column only.
    save_quality(
        report_id,
        result={
            "pass": False,
            "confidence": 0.0,
            "has_coherent_framework": False,
            "has_broad_sector_coverage": False,
            "scope": "unclear",
            "topic": "",
            "short_title": "",
            "framework_summary": None,
            "fail_reasons": ["extract_or_api_error"],
            "pass_signals": [],
            "rationale": "텍스트 추출 또는 감사 API 호출에 실패했습니다.",
            "themes": [],
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
            {"role": "system", "content": system_prompt_for_source(target.source)},
            {
                "role": "user",
                "content": (
                    f"Title: {target.title}\n"
                    f"Source: {target.source}\n\n"
                    f"Article / report text (extracted from early pages):\n{target.text}"
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
    result = apply_source_pass_policy(result, target.source)
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
    source: str | None = None,
    report_id: UUID | str | None = None,
    non_korean_summary: bool = False,
) -> dict[str, int]:
    rows = fetch_targets(
        force=force,
        limit=limit,
        theme=theme,
        source=source,
        report_id=report_id,
        non_korean_summary=non_korean_summary,
    )
    print(
        f"candidates={len(rows)} force={force} theme={theme} "
        f"source={source} report_id={report_id} "
        f"non_korean_summary={non_korean_summary} "
        f"concurrency={concurrency}"
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
