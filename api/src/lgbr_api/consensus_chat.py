"""Compare-chat SSE: OpenRouter tool loop + SerpAPI web_search, then stream answer."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Any

from lgbr_api.consensus_api import (
    DEFAULT_MODEL,
    OPENROUTER_URL,
    THEMES,
    _openrouter_key,
    get_latest_ended,
    get_outputs,
)
from lgbr_api.db import load_database_env

MAX_TOOL_ROUNDS = 3
WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the live web via Google (SerpAPI). "
            "Use for fresh facts, prices, news, or items not in the consensus frame."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (Korean or English)",
                }
            },
            "required": ["query"],
        },
    },
}


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _serpapi_key() -> str:
    load_database_env()
    key = (
        os.environ.get("SERPAPI_API_KEY")
        or os.environ.get("SERPAPI_KEY")
        or ""
    ).strip()
    if not key:
        raise RuntimeError("SERPAPI_KEY (or SERPAPI_API_KEY) is not set")
    return key


def web_search(query: str, *, num: int = 5) -> list[dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []
    params = urllib.parse.urlencode(
        {
            "engine": "google",
            "q": q,
            "api_key": _serpapi_key(),
            "num": str(num),
            "hl": "ko",
        }
    )
    url = f"https://serpapi.com/search.json?{params}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    out: list[dict[str, str]] = []
    for item in (data.get("organic_results") or [])[:num]:
        out.append(
            {
                "title": str(item.get("title") or ""),
                "link": str(item.get("link") or ""),
                "snippet": str(item.get("snippet") or ""),
            }
        )
    return out


def _or_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_openrouter_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/lgbr",
        "X-Title": "lgbr-consensus-compare",
    }


def _or_chat(
    messages: list[dict[str, Any]],
    *,
    model: str,
    tools: list[dict[str, Any]] | None = None,
    stream: bool = False,
    temperature: float = 0.3,
) -> Any:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": stream,
        "reasoning": {"effort": "none"},
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if stream:
        payload["stream_options"] = {"include_usage": True}
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(payload).encode(),
        headers={
            **_or_headers(),
            **({"Accept": "text/event-stream"} if stream else {}),
        },
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=180)


def _clean_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    clean: list[dict[str, str]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip().lower()
        content = str(m.get("content") or "").strip()
        if role not in {"user", "assistant", "system"} or not content:
            continue
        clean.append({"role": role, "content": content})
    return clean


def _build_system(
    mode: str, *, theme: str | None, run_id: str | None
) -> tuple[list[dict[str, Any]], str | None, str | None, str | None]:
    """Returns (sys_messages, error_message, resolved_run_id, resolved_theme)."""
    base_tools = (
        "You may call web_search when you need live/public facts beyond your context. "
        "After searching, answer with citations (title + URL) when using web results. "
        "Reply in Korean unless the user asks otherwise."
    )
    resolved_run_id = run_id
    resolved_theme = theme if theme in THEMES else None

    if mode == "grounded":
        frame = None
        if not resolved_run_id and resolved_theme:
            latest = get_latest_ended(theme=resolved_theme)
            if not latest.get("ok"):
                return [], str(latest.get("message") or "latest failed"), None, None
            run = latest.get("run")
            if not run:
                return (
                    [],
                    f"no ended run for theme={resolved_theme}",
                    None,
                    resolved_theme,
                )
            resolved_run_id = str(run["id"])
            frame = latest.get("filled_frame") or latest.get("consensus_frame")
        elif resolved_run_id:
            out = get_outputs(resolved_run_id)
            if not out.get("ok"):
                return [], str(out.get("message") or "run not found"), None, None
            if out.get("state") != "ended":
                return (
                    [],
                    f"run state is {out.get('state')}, need ended",
                    resolved_run_id,
                    out.get("theme"),
                )
            frame = out.get("filled_frame") or out.get("consensus_frame")
            resolved_theme = out.get("theme") or resolved_theme
        else:
            return [], "theme or run_id required for grounded", None, None
        if not frame:
            return (
                [],
                "run has no filled_frame/consensus_frame yet",
                resolved_run_id,
                resolved_theme,
            )
        sys_content = (
            "You answer using the consensus filled frame as primary context. "
            "Prefer frame facts/structure; use web_search for gaps or updates. "
            f"{base_tools}\n\n"
            f"--- CONSENSUS FRAME ---\n{frame}\n--- END FRAME ---"
        )
    elif mode == "plain":
        sys_content = (
            "You are a helpful research assistant with optional web_search. "
            "No consensus frame is provided. "
            f"{base_tools}"
        )
    else:
        return [], "mode must be plain or grounded", None, None

    return (
        [{"role": "system", "content": sys_content}],
        None,
        resolved_run_id if mode == "grounded" else None,
        resolved_theme,
    )


def _parse_tool_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {"query": raw}
    return {}


def iter_compare_chat_sse(
    *,
    mode: str,
    messages: list[dict[str, Any]],
    run_id: str | None = None,
    theme: str | None = None,
    model: str | None = None,
) -> Iterator[str]:
    clean = _clean_messages(messages)
    if not any(m["role"] == "user" for m in clean):
        yield _sse("error", {"message": "at least one user message required"})
        return

    use_model = (model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    sys_msgs, err, resolved_run_id, resolved_theme = _build_system(
        mode, theme=theme, run_id=run_id
    )
    if err:
        yield _sse("error", {"message": err})
        return

    chain: list[dict[str, Any]] = list(sys_msgs) + [
        m for m in clean if m["role"] != "system"
    ]

    try:
        yield _sse("status", {"phase": "planning"})
        used_tools = False
        early_answer: str | None = None

        for _round in range(MAX_TOOL_ROUNDS):
            with _or_chat(
                chain, model=use_model, tools=[WEB_SEARCH_TOOL], stream=False
            ) as resp:
                data = json.loads(resp.read().decode())
            if data.get("error"):
                yield _sse(
                    "error",
                    {"message": json.dumps(data["error"], ensure_ascii=False)},
                )
                return
            choices = data.get("choices") or []
            if not choices:
                yield _sse("error", {"message": "empty choices"})
                return
            msg = choices[0].get("message") or {}
            tool_calls = msg.get("tool_calls") or []
            content = (msg.get("content") or "").strip()

            if not tool_calls:
                if not used_tools and content:
                    # No search needed — reuse this completion (avoid a second call).
                    early_answer = content
                break

            used_tools = True
            yield _sse("status", {"phase": "search"})
            chain.append(
                {
                    "role": "assistant",
                    "content": msg.get("content"),
                    "tool_calls": tool_calls,
                }
            )
            for tc in tool_calls:
                fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
                name = str(fn.get("name") or "")
                args = _parse_tool_args(fn.get("arguments"))
                tc_id = str(tc.get("id") or "")
                results: list[dict[str, str]] = []
                query = ""
                if name != "web_search":
                    tool_payload: dict[str, Any] = {"error": f"unknown tool {name}"}
                else:
                    query = str(args.get("query") or "").strip()
                    try:
                        results = web_search(query)
                        tool_payload = {"query": query, "results": results}
                    except Exception as exc:
                        yield _sse(
                            "error", {"message": f"web_search failed: {exc}"}
                        )
                        return
                yield _sse(
                    "tool",
                    {"name": "web_search", "query": query, "results": results},
                )
                chain.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps(tool_payload, ensure_ascii=False),
                    }
                )

        yield _sse("status", {"phase": "answer", "searched": used_tools})
        if early_answer is not None:
            # Soft-stream in chunks for UI parity.
            step = 48
            for i in range(0, len(early_answer), step):
                yield _sse("delta", {"text": early_answer[i : i + step]})
        else:
            with _or_chat(chain, model=use_model, tools=None, stream=True) as resp:
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
                        yield _sse(
                            "error",
                            {
                                "message": json.dumps(
                                    chunk["error"], ensure_ascii=False
                                )
                            },
                        )
                        return
                    ch0 = (chunk.get("choices") or [{}])[0]
                    piece = (ch0.get("delta") or {}).get("content") or ""
                    if piece:
                        yield _sse("delta", {"text": piece})

        yield _sse(
            "done",
            {
                "ok": True,
                "mode": mode,
                "model": use_model,
                "run_id": resolved_run_id,
                "theme": resolved_theme,
            },
        )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:800]
        yield _sse("error", {"message": f"OpenRouter HTTP {exc.code}: {body}"})
    except Exception as exc:
        yield _sse("error", {"message": str(exc)})
