"""Eval: agentic SerpAPI baseline vs filled_frame knowledge graphs (SSE)."""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any

from lgbr_api.consensus_api import (
    DEFAULT_MODEL,
    OPENROUTER_URL,
    _openrouter_key,
    _parse_jsonb,
    get_outputs,
)
from lgbr_api.consensus_chat import (
    WEB_SEARCH_TOOL,
    _normalize_assistant_tools,
    _or_chat,
    _parse_tool_args,
    _strip_dsml,
    resolve_search_locale,
    web_search,
)
from lgbr_api.db import connect

MAX_AGENT_ROUNDS = 4
MAX_SUCCESSFUL_SEARCHES = 6
CLAIMS_PER_AXIS = 8
STALE_MINUTES = 20
MIN_BASELINE_CHARS = 2500
WRITE_MAX_TOKENS = 8192
WRITE_SOURCES_PER_QUERY = 5

THEME_LABEL = {
    "ai": "AI",
    "datacenter": "데이터센터",
    "macroeconomy": "거시경제",
    "physical_ai": "피지컬 AI",
    "appliance": "가전",
    "display": "디스플레이",
    "automotive": "자동차",
    "petrochemical": "석유화학",
}

_JSON_FENCE = re.compile(
    r"```(?:json)?\s*([\s\S]*?)```",
    re.IGNORECASE,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _serialize_eval(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": str(row["id"]),
        "run_id": str(row["run_id"]),
        "state": row["state"],
        "baseline_md": row.get("baseline_md"),
        "serp_queries": _parse_jsonb(row.get("serp_queries") or []),
        # serp_hits omitted from GET — large, unused by UI (stream tool events keep hits)
        "graph_ours": _parse_jsonb(row.get("graph_ours")),
        "graph_baseline": _parse_jsonb(row.get("graph_baseline")),
        "checklist": _parse_jsonb(row.get("checklist")),
        "error": row.get("error"),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "started_at": row["started_at"].isoformat() if row.get("started_at") else None,
        "finished_at": (
            row["finished_at"].isoformat() if row.get("finished_at") else None
        ),
        "query_count": len(_parse_jsonb(row.get("serp_queries") or []) or []),
    }


def _mark_stale_evals(run_id: str | None = None) -> int:
    """Flip abandoned running/pending rows to error. Returns count."""
    cutoff = _now() - timedelta(minutes=STALE_MINUTES)
    with connect() as conn, conn.cursor() as cur:
        if run_id:
            cur.execute(
                """
                UPDATE consensus_evals
                SET state = 'error',
                    error = COALESCE(error, 'interrupted (stale or process restart)'),
                    finished_at = %s
                WHERE run_id = %s::uuid
                  AND state IN ('pending', 'running')
                  AND started_at IS NOT NULL
                  AND started_at < %s
                """,
                (_now(), run_id, cutoff),
            )
        else:
            cur.execute(
                """
                UPDATE consensus_evals
                SET state = 'error',
                    error = COALESCE(error, 'interrupted (stale or process restart)'),
                    finished_at = %s
                WHERE state IN ('pending', 'running')
                  AND started_at IS NOT NULL
                  AND started_at < %s
                """,
                (_now(), cutoff),
            )
        n = cur.rowcount or 0
        conn.commit()
    return n


def mark_all_open_evals_interrupted(
    reason: str = "interrupted (process restart)",
) -> int:
    """SSE evals cannot resume across process restart — close all open rows."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE consensus_evals
            SET state = 'error',
                error = COALESCE(error, %s),
                finished_at = %s
            WHERE state IN ('pending', 'running')
            """,
            (reason, _now()),
        )
        n = cur.rowcount or 0
        conn.commit()
    return n


def get_eval(run_id: str) -> dict[str, Any]:
    _mark_stale_evals(run_id)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM consensus_evals
            WHERE run_id = %s::uuid
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (run_id,),
        )
        row = cur.fetchone()
    if not row:
        return {"ok": True, "eval": None}
    return {"ok": True, "eval": _serialize_eval(row)}


def _load_run_for_eval(run_id: str) -> dict[str, Any]:
    """Validate run and return context or error dict with ok=False."""
    run_id = (run_id or "").strip()
    if not run_id:
        return {"ok": False, "status": 400, "message": "run_id required"}

    out = get_outputs(run_id)
    if not out.get("ok"):
        return out
    if out.get("state") != "ended":
        return {
            "ok": False,
            "status": 400,
            "message": f"run state is {out.get('state')}, need ended",
        }
    filled = (out.get("filled_frame") or "").strip()
    if not filled:
        return {"ok": False, "status": 400, "message": "filled_frame missing"}

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, theme, criteria, state
            FROM consensus_runs WHERE id = %s::uuid
            """,
            (run_id,),
        )
        run = cur.fetchone()
    if not run:
        return {"ok": False, "status": 404, "message": "run not found"}
    criteria = _parse_jsonb(run.get("criteria") or {})
    if not isinstance(criteria, dict):
        criteria = {}
    pillars = [
        str(p).strip()
        for p in (criteria.get("pillar_sketch") or [])
        if str(p).strip()
    ]
    thesis = str(criteria.get("thesis") or "").strip()
    if len(pillars) < 2:
        return {
            "ok": False,
            "status": 400,
            "message": "분석 축(pillar_sketch)이 필요합니다",
        }
    return {
        "ok": True,
        "run_id": run_id,
        "theme": str(run["theme"]),
        "thesis": thesis,
        "pillars": pillars,
        "filled_md": filled,
    }


def _interrupt_open_evals(run_id: str) -> None:
    """Any still-open eval for this run → error (new stream takes over)."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE consensus_evals
            SET state = 'error',
                error = 'interrupted (superseded)',
                finished_at = %s
            WHERE run_id = %s::uuid AND state IN ('pending', 'running')
            """,
            (_now(), run_id),
        )
        conn.commit()


def _create_eval_row(run_id: str) -> dict[str, Any]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO consensus_evals (run_id, state, started_at)
            VALUES (%s::uuid, 'running', %s)
            RETURNING *
            """,
            (run_id, _now()),
        )
        row = cur.fetchone()
        conn.commit()
    return row


def start_eval(run_id: str) -> dict[str, Any]:
    """Non-stream entry: validate readiness; actual work is POST .../eval/stream."""
    _mark_stale_evals(run_id)
    ctx = _load_run_for_eval(run_id)
    if not ctx.get("ok"):
        return ctx
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM consensus_evals
            WHERE run_id = %s::uuid
            ORDER BY created_at DESC LIMIT 1
            """,
            (run_id,),
        )
        latest = cur.fetchone()
    return {
        "ok": True,
        "status": 200,
        "eval": _serialize_eval(latest),
        "message": "use POST .../eval/stream to run with live progress",
    }


def _set_eval(
    eval_id: str,
    *,
    state: str | None = None,
    baseline_md: str | None = None,
    serp_queries: list[Any] | None = None,
    serp_hits: list[Any] | None = None,
    graph_ours: dict[str, Any] | None = None,
    graph_baseline: dict[str, Any] | None = None,
    checklist: dict[str, Any] | None = None,
    error: str | None = None,
    finished: bool = False,
) -> None:
    sets: list[str] = []
    args: list[Any] = []
    if state is not None:
        sets.append("state = %s")
        args.append(state)
    if baseline_md is not None:
        sets.append("baseline_md = %s")
        args.append(baseline_md)
    if serp_queries is not None:
        sets.append("serp_queries = %s::jsonb")
        args.append(json.dumps(serp_queries, ensure_ascii=False))
    if serp_hits is not None:
        sets.append("serp_hits = %s::jsonb")
        args.append(json.dumps(serp_hits, ensure_ascii=False))
    if graph_ours is not None:
        sets.append("graph_ours = %s::jsonb")
        args.append(json.dumps(graph_ours, ensure_ascii=False))
    if graph_baseline is not None:
        sets.append("graph_baseline = %s::jsonb")
        args.append(json.dumps(graph_baseline, ensure_ascii=False))
    if checklist is not None:
        sets.append("checklist = %s::jsonb")
        args.append(json.dumps(checklist, ensure_ascii=False))
    if error is not None:
        sets.append("error = %s")
        args.append(error)
    if finished:
        sets.append("finished_at = %s")
        args.append(_now())
    if not sets:
        return
    args.append(eval_id)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE consensus_evals SET {', '.join(sets)} WHERE id = %s::uuid",
            args,
        )
        conn.commit()


def iter_eval_sse(run_id: str) -> Iterator[str]:
    """Run full eval pipeline while yielding SSE events."""
    _mark_stale_evals(run_id)
    ctx = _load_run_for_eval(run_id)
    if not ctx.get("ok"):
        yield _sse(
            "error",
            {"message": str(ctx.get("message") or "eval failed"), "status": ctx.get("status")},
        )
        return

    _interrupt_open_evals(run_id)
    row = _create_eval_row(run_id)
    eval_id = str(row["id"])
    theme = ctx["theme"]
    thesis = ctx["thesis"]
    pillars = ctx["pillars"]
    filled_md = ctx["filled_md"]

    yield _sse(
        "result",
        {"eval_id": eval_id, "query_count": 0, "state": "running"},
    )

    queries: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    baseline_md = ""

    try:
        yield _sse("status", {"phase": "gathering"})
        collected: list[tuple[str, list[dict[str, str]]]] = []
        for ev in _iter_baseline_gather(theme=theme, thesis=thesis, pillars=pillars):
            kind = ev["kind"]
            if kind == "tool":
                queries.append(
                    {
                        "query": ev.get("query"),
                        "gl": ev.get("gl"),
                        "hl": ev.get("hl"),
                        **({"error": ev["error"]} if ev.get("error") else {}),
                    }
                )
                hits.append(
                    {
                        "query": ev.get("query"),
                        "gl": ev.get("gl"),
                        "hl": ev.get("hl"),
                        "results": ev.get("results") or [],
                        **({"error": ev["error"]} if ev.get("error") else {}),
                    }
                )
                _set_eval(eval_id, serp_queries=queries, serp_hits=hits)
                yield _sse(
                    "tool",
                    {
                        "query": ev.get("query"),
                        "gl": ev.get("gl"),
                        "hl": ev.get("hl"),
                        "results": ev.get("results") or [],
                        "error": ev.get("error"),
                        "query_count": len(queries),
                    },
                )
                yield _sse(
                    "result",
                    {
                        "eval_id": eval_id,
                        "query_count": len(queries),
                        "state": "running",
                    },
                )
            elif kind == "collected":
                collected = list(ev.get("collected") or [])
                break

        yield _sse("status", {"phase": "writing"})
        for ev in _iter_baseline_write(
            theme=theme,
            thesis=thesis,
            pillars=pillars,
            collected=collected,
        ):
            if ev["kind"] == "delta":
                baseline_md += ev["text"]
                yield _sse("delta", {"text": ev["text"]})
            elif ev["kind"] == "done":
                baseline_md = ev.get("text") or baseline_md

        baseline_md = (baseline_md or "").strip()
        if len(baseline_md) < MIN_BASELINE_CHARS:
            raise RuntimeError(
                f"baseline too short ({len(baseline_md)} chars; "
                f"need ≥{MIN_BASELINE_CHARS})"
            )
        if "Executive Summary" not in baseline_md or "주제별 Deep Dive" not in baseline_md:
            raise RuntimeError(
                "baseline missing required sections "
                "(Executive Summary / 주제별 Deep Dive)"
            )
        banned = ("LGERI", "LG Economic Research", "LG 경제연구", "경제연구원")
        if any(b in baseline_md for b in banned):
            raise RuntimeError("baseline contains forbidden org/brand names")
        _set_eval(
            eval_id,
            baseline_md=baseline_md,
            serp_queries=queries,
            serp_hits=hits,
        )

        yield _sse("status", {"phase": "graph_ours"})
        graph_ours = _extract_and_verify_graph(filled_md, pillars, side="ours")
        _set_eval(eval_id, graph_ours=graph_ours)

        yield _sse("status", {"phase": "graph_baseline"})
        graph_baseline = _extract_and_verify_graph(
            baseline_md, pillars, side="baseline"
        )
        _set_eval(
            eval_id,
            state="ended",
            graph_ours=graph_ours,
            graph_baseline=graph_baseline,
            finished=True,
        )
        yield _sse(
            "graphs",
            {
                "graph_ours": graph_ours,
                "graph_baseline": graph_baseline,
            },
        )
        yield _sse(
            "status",
            {
                "phase": "done",
                "eval_id": eval_id,
                "query_count": len(queries),
            },
        )
    except GeneratorExit:
        _set_eval(
            eval_id,
            state="error",
            error="client disconnected",
            serp_queries=queries or None,
            serp_hits=hits or None,
            baseline_md=baseline_md or None,
            finished=True,
        )
        raise
    except Exception as exc:
        _set_eval(
            eval_id,
            state="error",
            error=str(exc)[:2000],
            serp_queries=queries or None,
            serp_hits=hits or None,
            baseline_md=baseline_md or None,
            finished=True,
        )
        yield _sse("error", {"message": str(exc)[:2000], "eval_id": eval_id})


def _iter_baseline_gather(
    *, theme: str, thesis: str, pillars: list[str]
) -> Iterator[dict[str, Any]]:
    sector = THEME_LABEL.get(theme, theme)
    pillars_block = "\n".join(f"- {p}" for p in pillars)
    thesis_line = thesis or "(thesis not provided)"
    system = (
        "You gather web sources for a Korean industry-trends report draft. "
        "You do NOT have broker research PDFs. "
        "Use web_search only — invent short queries (3–8 keywords). "
        "Korean query → hl=ko gl=kr; English → hl=en gl=us. "
        "Do NOT write the final report body in this phase. "
        "Do NOT invent organization or institute brand names. "
        "When you have enough material for the given analysis axes, stop calling tools "
        "and reply briefly that gathering is done."
    )
    user = (
        f"Sector: {sector}\n"
        f"Thesis / tension: {thesis_line}\n"
        f"Analysis axes:\n{pillars_block}\n\n"
        "Gather web material with web_search for a report covering these axes. "
        f"About {MAX_SUCCESSFUL_SEARCHES} successful searches is enough. "
        "Do not write the final report body."
    )
    model = DEFAULT_MODEL
    chain: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    collected: list[tuple[str, list[dict[str, str]]]] = []

    for _ in range(MAX_AGENT_ROUNDS):
        if len(collected) >= MAX_SUCCESSFUL_SEARCHES:
            break
        with _or_chat(
            chain, model=model, tools=[WEB_SEARCH_TOOL], stream=False
        ) as resp:
            data = json.loads(resp.read().decode())
        if data.get("error"):
            raise RuntimeError(json.dumps(data["error"], ensure_ascii=False))
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("empty choices in baseline agent")
        msg = choices[0].get("message") or {}
        native_tools = bool(msg.get("tool_calls"))
        tool_calls, prose = _normalize_assistant_tools(msg)

        if not tool_calls:
            if collected:
                yield {"kind": "collected", "collected": collected}
                return
            if prose:
                chain.append({"role": "assistant", "content": prose})
                chain.append(
                    {
                        "role": "user",
                        "content": (
                            "You have not searched yet. Call web_search to gather sources. "
                            "Do not write the report body."
                        ),
                    }
                )
                continue
            break

        if native_tools:
            chain.append(
                {
                    "role": "assistant",
                    "content": prose or None,
                    "tool_calls": tool_calls,
                }
            )
        else:
            chain.append(
                {"role": "assistant", "content": prose or "(web_search)"}
            )

        result_blobs: list[str] = []
        for tc in tool_calls:
            if len(collected) >= MAX_SUCCESSFUL_SEARCHES:
                break
            fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
            name = str(fn.get("name") or "")
            args = _parse_tool_args(fn.get("arguments"))
            tc_id = str(tc.get("id") or "")
            results: list[dict[str, str]] = []
            query = ""
            gl = "us"
            hl = "en"
            if name != "web_search":
                tool_payload: dict[str, Any] = {"error": f"unknown tool {name}"}
            else:
                query = str(args.get("query") or "").strip()
                gl, hl = resolve_search_locale(
                    query, args.get("gl"), args.get("hl")
                )
                try:
                    results = web_search(query, gl=gl, hl=hl, num=8)
                    tool_payload = {
                        "query": query,
                        "gl": gl,
                        "hl": hl,
                        "results": results,
                    }
                    if not results:
                        tool_payload["error"] = (
                            "No results. Retry with different hl/gl or query."
                        )
                    else:
                        collected.append((query, results))
                except Exception as exc:
                    tool_payload = {
                        "query": query,
                        "gl": gl,
                        "hl": hl,
                        "results": [],
                        "error": str(exc),
                    }
            yield {
                "kind": "tool",
                "query": query,
                "gl": gl,
                "hl": hl,
                "results": results,
                "error": tool_payload.get("error"),
            }
            blob = json.dumps(tool_payload, ensure_ascii=False)
            result_blobs.append(blob)
            if native_tools:
                chain.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": blob,
                    }
                )
        if not native_tools and result_blobs:
            chain.append(
                {
                    "role": "user",
                    "content": (
                        "web_search results:\n"
                        + "\n\n".join(result_blobs)
                        + "\n\nIf you need more, call web_search again. "
                        "If enough, reply briefly with no tools that gathering is done. "
                        "Do not write the final report."
                    ),
                }
            )

    yield {"kind": "collected", "collected": collected}


def _source_blocks(
    collected: list[tuple[str, list[dict[str, str]]]],
) -> str:
    blocks: list[str] = []
    for query, results in collected[:MAX_SUCCESSFUL_SEARCHES]:
        slim = []
        for r in (results or [])[:WRITE_SOURCES_PER_QUERY]:
            if not isinstance(r, dict):
                continue
            slim.append(
                {
                    "title": r.get("title") or "",
                    "link": r.get("link") or "",
                    "snippet": (r.get("snippet") or "")[:280],
                }
            )
        blocks.append(
            f"### web_search: {query}\n"
            + json.dumps(slim, ensure_ascii=False)
        )
    return "\n\n".join(blocks)


def _baseline_template(pillars: list[str]) -> str:
    # Output headers stay Korean to match filled_frame; instructions elsewhere are English.
    topics = "\n".join(
        f"### {i}. {p}\n"
        f"- **주제 역할**\n"
        f"- **Claim**\n"
        f"- **Evidence** (source title/URL)\n"
        f"- **현황 및 전망**\n"
        f"- **주요 플레이어**\n"
        f"- **성장·저해 요인**\n"
        f"- **Watch**"
        for i, p in enumerate(pillars, start=1)
    )
    return (
        "# 살 붙인 논지\n\n"
        "## Executive Summary\n"
        "(full prose)\n\n"
        "## 주제별 Deep Dive\n"
        f"{topics}\n\n"
        "## 미충족 보강\n"
        "- …\n\n"
        "## 참고 (웹 출처)\n"
        "- title — URL\n"
    )


def _iter_baseline_write(
    *,
    theme: str,
    thesis: str,
    pillars: list[str],
    collected: list[tuple[str, list[dict[str, str]]]],
) -> Iterator[dict[str, Any]]:
    sector = THEME_LABEL.get(theme, theme)
    thesis_line = thesis or "(thesis not provided)"
    template = _baseline_template(pillars)
    system = (
        "You draft a Korean industry-trends report from web_search results only. "
        "Match the section headers in the template EXACTLY — do not rename them "
        "(Korean headers are intentional; keep them verbatim). "
        "Write the body in Korean. "
        "Deep Dive ### N. titles must be the given analysis axes in order. "
        "Never invent institute or brand names (no LGERI, no research-institute letterhead). "
        "Do not claim affiliation with any company or institute. "
        "Cite web sources with title/URL. No speculation beyond sources."
    )
    sources = _source_blocks(collected) if collected else "(no search results)"
    user = (
        f"Sector: {sector}\n"
        f"Thesis / tension: {thesis_line}\n\n"
        "Keep the template headers exactly. Write a sufficiently long Korean report "
        f"using only the web search results (aim for at least ~{MIN_BASELINE_CHARS} characters).\n\n"
        f"## Template (headers exact)\n{template}\n\n"
        f"## Web search results\n{sources}\n"
    )
    answer_chain: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    model = DEFAULT_MODEL

    def _stream_once(chain: list[dict[str, Any]]) -> Iterator[str]:
        with _or_chat(
            chain,
            model=model,
            tools=None,
            stream=True,
            max_tokens=WRITE_MAX_TOKENS,
        ) as resp:
            while True:
                line = resp.readline()
                if not line:
                    break
                line_s = line.decode("utf-8", errors="replace").strip()
                if not line_s.startswith("data:"):
                    continue
                data_s = line_s[5:].strip()
                if data_s == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_s)
                except json.JSONDecodeError:
                    continue
                if chunk.get("error"):
                    raise RuntimeError(
                        json.dumps(chunk["error"], ensure_ascii=False)
                    )
                ch0 = (chunk.get("choices") or [{}])[0]
                piece = (ch0.get("delta") or {}).get("content") or ""
                if piece:
                    yield piece

    def _complete_once(chain: list[dict[str, Any]]) -> str:
        with _or_chat(
            chain,
            model=model,
            tools=None,
            stream=False,
            max_tokens=WRITE_MAX_TOKENS,
        ) as resp:
            data = json.loads(resp.read().decode())
        if data.get("error"):
            raise RuntimeError(json.dumps(data["error"], ensure_ascii=False))
        msg = ((data.get("choices") or [{}])[0].get("message") or {})
        return _strip_dsml(str(msg.get("content") or "")).strip()

    answer_text = ""
    for piece in _stream_once(answer_chain):
        answer_text += piece

    text = _strip_dsml(answer_text).strip()
    if len(text) < MIN_BASELINE_CHARS:
        retry_chain = list(answer_chain) + [
            {"role": "assistant", "content": text or "(empty)"},
            {
                "role": "user",
                "content": (
                    f"Output is too short ({len(text)} characters). "
                    "Keep the same template headers and complete Executive Summary "
                    "and every Deep Dive axis so the report is at least "
                    f"{MIN_BASELINE_CHARS} characters. "
                    "No institute or brand letterhead."
                ),
            },
        ]
        text = _complete_once(retry_chain)

    if not text:
        raise RuntimeError("baseline report empty")
    step = 80
    for i in range(0, len(text), step):
        yield {"kind": "delta", "text": text[i : i + step]}
    yield {"kind": "done", "text": text}


def _extract_json_obj(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    m = _JSON_FENCE.search(raw)
    if m:
        raw = m.group(1).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        data = json.loads(raw[start : end + 1])
        if isinstance(data, dict):
            return data
    raise RuntimeError("failed to parse graph JSON")


def _or_json_chat(messages: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "model": DEFAULT_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "stream": False,
        "reasoning": {"effort": "none"},
    }
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {_openrouter_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/lgbr",
            "X-Title": "lgbr-consensus-eval",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise RuntimeError(json.dumps(data["error"], ensure_ascii=False))
    choices = data.get("choices") or []
    content = str((choices[0].get("message") or {}).get("content") or "")
    return _extract_json_obj(content)


def _extract_and_verify_graph(
    body_md: str, pillars: list[str], *, side: str
) -> dict[str, Any]:
    axis_ids = [f"axis_{i}" for i in range(len(pillars))]
    axes_list = [
        {"id": axis_ids[i], "label": pillars[i]} for i in range(len(pillars))
    ]
    prompt = (
        "Extract a knowledge graph from the report for perspective breadth/depth.\n"
        "Return ONLY JSON with shape:\n"
        '{"nodes":[{"id","type","label","quote","axis_id"}],'
        '"edges":[{"source","target","type"}]}\n'
        "Rules:\n"
        f"- Fixed axis nodes (include all): {json.dumps(axes_list, ensure_ascii=False)}\n"
        "- type for axes is \"axis\"; for claims is \"claim\".\n"
        "- Each claim MUST have quote: exact substring copied from the report.\n"
        f"- At most {CLAIMS_PER_AXIS} claims per axis.\n"
        "- claim.axis_id must be one of the fixed axis ids.\n"
        "- edges.type is belongs | deepens | disagrees.\n"
        "- belongs: axis -> claim. deepens/disagrees: claim -> claim.\n"
        "- Do not invent facts; only use text present in the report.\n"
    )
    data = _or_json_chat(
        [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": f"--- REPORT ({side}) ---\n{body_md}\n--- END ---",
            },
        ]
    )
    return _verify_graph(data, body_md, pillars, axis_ids)


def _norm_quote(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip())


def _quote_in_body(quote: str, body: str) -> bool:
    q = (quote or "").strip()
    if len(q) < 8:
        return False
    if q in body:
        return True
    return _norm_quote(q) in _norm_quote(body)


def _verify_graph(
    raw: dict[str, Any],
    body_md: str,
    pillars: list[str],
    axis_ids: list[str],
) -> dict[str, Any]:
    axis_nodes = [
        {
            "id": axis_ids[i],
            "type": "axis",
            "label": pillars[i],
            "quote": None,
            "axis_id": axis_ids[i],
        }
        for i in range(len(pillars))
    ]
    claims_in: list[dict[str, Any]] = []
    for n in raw.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        if str(n.get("type") or "") != "claim":
            continue
        quote = str(n.get("quote") or "").strip()
        axis_id = str(n.get("axis_id") or "").strip()
        if axis_id not in axis_ids:
            continue
        if not _quote_in_body(quote, body_md):
            continue
        cid = str(n.get("id") or "").strip() or f"claim_{len(claims_in)}"
        claims_in.append(
            {
                "id": cid,
                "type": "claim",
                "label": str(n.get("label") or quote[:40]),
                "quote": quote,
                "axis_id": axis_id,
            }
        )

    by_axis: dict[str, list[dict[str, Any]]] = {a: [] for a in axis_ids}
    for c in claims_in:
        bucket = by_axis[c["axis_id"]]
        if len(bucket) < CLAIMS_PER_AXIS:
            bucket.append(c)
    claims = [c for a in axis_ids for c in by_axis[a]]
    claim_ids = {c["id"] for c in claims}
    axis_set = set(axis_ids)

    edges_out: list[dict[str, Any]] = []
    for e in raw.get("edges") or []:
        if not isinstance(e, dict):
            continue
        src = str(e.get("source") or "").strip()
        tgt = str(e.get("target") or "").strip()
        et = str(e.get("type") or "").strip()
        if et == "belongs":
            if src in axis_set and tgt in claim_ids:
                edges_out.append({"source": src, "target": tgt, "type": "belongs"})
        elif et in ("deepens", "disagrees"):
            if src in claim_ids and tgt in claim_ids and src != tgt:
                edges_out.append({"source": src, "target": tgt, "type": et})

    have_belongs = {
        (e["source"], e["target"]) for e in edges_out if e["type"] == "belongs"
    }
    for c in claims:
        key = (c["axis_id"], c["id"])
        if key not in have_belongs:
            edges_out.append(
                {"source": c["axis_id"], "target": c["id"], "type": "belongs"}
            )

    raw_claim_n = sum(
        1
        for n in (raw.get("nodes") or [])
        if isinstance(n, dict) and str(n.get("type") or "") == "claim"
    )
    return {
        "nodes": axis_nodes + claims,
        "edges": edges_out,
        "meta": {
            "claims_raw": raw_claim_n,
            "claims_verified": len(claims),
            "quote_pass_rate": (
                (len(claims) / raw_claim_n) if raw_claim_n else None
            ),
        },
    }


def _claim_labels(graph: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for n in graph.get("nodes") or []:
        if str(n.get("type") or "") == "claim":
            out.add(str(n.get("label") or "").strip())
    return {x for x in out if x}


def _build_checklist(
    graph_ours: dict[str, Any],
    graph_baseline: dict[str, Any],
    pillars: list[str],
) -> dict[str, Any]:
    axis_ids = [f"axis_{i}" for i in range(len(pillars))]

    def per_axis(g: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for i, aid in enumerate(axis_ids):
            claims = [
                n
                for n in (g.get("nodes") or [])
                if n.get("type") == "claim" and n.get("axis_id") == aid
            ]
            rows.append(
                {
                    "axis_id": aid,
                    "axis": pillars[i],
                    "claims": len(claims),
                }
            )
        return rows

    def edge_counts(g: dict[str, Any]) -> dict[str, int]:
        deep = sum(1 for e in (g.get("edges") or []) if e.get("type") == "deepens")
        dis = sum(1 for e in (g.get("edges") or []) if e.get("type") == "disagrees")
        return {"deepens": deep, "disagrees": dis}

    ours_labels = _claim_labels(graph_ours)
    base_labels = _claim_labels(graph_baseline)
    only_ours = sorted(ours_labels - base_labels)
    only_base = sorted(base_labels - ours_labels)

    return {
        "ours": {
            "per_axis": per_axis(graph_ours),
            "edges": edge_counts(graph_ours),
            "quote_pass_rate": (graph_ours.get("meta") or {}).get("quote_pass_rate"),
            "claims_verified": (graph_ours.get("meta") or {}).get("claims_verified"),
        },
        "baseline": {
            "per_axis": per_axis(graph_baseline),
            "edges": edge_counts(graph_baseline),
            "quote_pass_rate": (graph_baseline.get("meta") or {}).get(
                "quote_pass_rate"
            ),
            "claims_verified": (graph_baseline.get("meta") or {}).get(
                "claims_verified"
            ),
        },
        "only_ours_labels": only_ours[:40],
        "only_baseline_labels": only_base[:40],
    }
