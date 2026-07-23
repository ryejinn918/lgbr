"""Compare-chat SSE: OpenRouter tool loop + SerpAPI web_search, then stream answer."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from lgbr_api.consensus_api import (
    DEFAULT_MODEL,
    OPENROUTER_URL,
    THEMES,
    _openrouter_key,
    get_latest_ended,
    get_outputs,
)
from lgbr_api.db import load_database_env
from lgbr_api.news_store import get_cached_search, upsert_search_results

_SEOUL = ZoneInfo("Asia/Seoul")

MAX_TOOL_ROUNDS = 3
WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search Google News via SerpAPI for recent headlines. "
            "Use for latest news and time-sensitive public facts beyond the "
            "~3-month broker-report consensus frame."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "News search query (Korean or English)",
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
    cached = get_cached_search(q)
    if cached is not None:
        return cached[:num]
    params = urllib.parse.urlencode(
        {
            "engine": "google_news",
            "q": q,
            "api_key": _serpapi_key(),
            "num": str(num),
            "gl": "us",
            "hl": "ko",
        }
    )
    url = f"https://serpapi.com/search.json?{params}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    items: list[dict[str, Any]] = []
    for item in (data.get("news_results") or [])[:num]:
        items.append(
            {
                "title": str(item.get("title") or ""),
                "link": str(item.get("link") or ""),
                "snippet": str(item.get("snippet") or ""),
                "date": item.get("date"),
                "publisher": str(item.get("source") or ""),
                "position": item.get("position"),
                "thumbnail": item.get("thumbnail"),
            }
        )
    return upsert_search_results(q, items)[:num]


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


def _today_seoul() -> str:
    now = datetime.now(_SEOUL)
    return now.strftime("%Y-%m-%d (%A)")


def _build_system(
    mode: str, *, theme: str | None, run_id: str | None
) -> tuple[list[dict[str, Any]], str | None, str | None, str | None]:
    """Returns (sys_messages, error_message, resolved_run_id, resolved_theme)."""
    today = _today_seoul()
    base = (
        f"Today is {today} in Asia/Seoul.\n"
        "You are writing for LG Economic Research Institute (LGERI) practitioners. "
        "Be concise and logical. Ground every claim in a source "
        "(frame report slug, or web title + URL). "
        "Avoid speculation and rhetoric; if unknown, say so. "
        "Reply in Korean unless the user asks otherwise. "
        "Call web_search (Google News) for live/public facts beyond your context; "
        "cite title + URL when using web results."
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
            f"{base}\n\n"
            "Primary context is the consensus filled frame below. "
            "It synthesizes broker research reports from roughly the last 3 months. "
            "It may miss same-day or very recent news, prices, and filings. "
            "For time-sensitive facts, use web_search (news), then answer citing frame "
            "vs news sources separately. Prefer the frame's structure and consensus "
            "pillars; if the news is newer and conflicts, state the dates and prefer "
            "the fresher fact.\n\n"
            f"--- CONSENSUS FRAME ---\n{frame}\n--- END FRAME ---"
        )
    elif mode == "plain":
        sys_content = (
            f"{base}\n\n"
            "No consensus frame is provided. "
            "Use web_search (Google News) to verify timely facts before answering."
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


# DeepSeek sometimes emits tool calls as DSML text in `content` instead of
# structured `tool_calls` (seen as <|DSML|…> with fullwidth bars ｜).
_DSML_MARK = re.compile(r"<\s*[|｜]\s*DSML\s*[|｜]", re.IGNORECASE)
_DSML_BLOCK = re.compile(
    r"<\s*[|｜]\s*DSML\s*[|｜]\s*tool_calls\s*>"
    r".*?"
    r"<\s*/\s*[|｜]\s*DSML\s*[|｜]\s*tool_calls\s*>",
    re.IGNORECASE | re.DOTALL,
)
_DSML_INVOKE = re.compile(
    r"<\s*[|｜]\s*DSML\s*[|｜]\s*invoke\s+name\s*=\s*[\"']([^\"']+)[\"']\s*>"
    r"(.*?)"
    r"<\s*/\s*[|｜]\s*DSML\s*[|｜]\s*invoke\s*>",
    re.IGNORECASE | re.DOTALL,
)
_DSML_PARAM = re.compile(
    r"<\s*[|｜]\s*DSML\s*[|｜]\s*parameter\s+name\s*=\s*[\"']([^\"']+)[\"'][^>]*>"
    r"(.*?)"
    r"<\s*/\s*[|｜]\s*DSML\s*[|｜]\s*parameter\s*>",
    re.IGNORECASE | re.DOTALL,
)


def _content_has_dsml(text: str) -> bool:
    return bool(text and _DSML_MARK.search(text))


def _strip_dsml(text: str) -> str:
    if not text:
        return ""
    cleaned = _DSML_BLOCK.sub("", text)
    # Drop leftover partial tags if any.
    cleaned = re.sub(
        r"<\s*/?\s*[|｜]\s*DSML\s*[|｜][^>]*>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def _tool_calls_from_dsml(content: str) -> list[dict[str, Any]]:
    """Parse DSML tool markup into OpenAI-style tool_calls."""
    if not content or not _content_has_dsml(content):
        return []
    out: list[dict[str, Any]] = []
    for i, m in enumerate(_DSML_INVOKE.finditer(content)):
        name = (m.group(1) or "").strip()
        body = m.group(2) or ""
        args: dict[str, Any] = {}
        for pm in _DSML_PARAM.finditer(body):
            key = (pm.group(1) or "").strip()
            val = (pm.group(2) or "").strip()
            if key:
                args[key] = val
        if not name:
            continue
        out.append(
            {
                "id": f"dsml_{i}_{name}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            }
        )
    return out


def _normalize_assistant_tools(
    msg: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    """Return (tool_calls, prose_content) handling DSML-in-content fallbacks."""
    tool_calls = list(msg.get("tool_calls") or [])
    content = str(msg.get("content") or "")
    if not tool_calls:
        tool_calls = _tool_calls_from_dsml(content)
    prose = _strip_dsml(content).strip()
    return tool_calls, prose


class _DsmlStreamFilter:
    """Strip DSML tool markup from streamed answer deltas."""

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, piece: str) -> str:
        if not piece:
            return ""
        self._buf += piece
        if not _content_has_dsml(self._buf) and "<" not in self._buf[-12:]:
            out = self._buf
            self._buf = ""
            return out
        # Hold back if an open DSML/tag might still be arriving.
        if re.search(r"<\s*[|｜]?\s*D?S?M?L?\s*[|｜]?\s*$", self._buf[-24:]):
            return ""
        if _DSML_MARK.search(self._buf) and not _DSML_BLOCK.search(self._buf):
            # Incomplete block — wait for more chunks (cap buffer).
            if len(self._buf) < 8000:
                return ""
        cleaned = _strip_dsml(self._buf)
        # If strip removed everything but buffer still growing mid-block, hold.
        if not cleaned and _content_has_dsml(self._buf):
            return ""
        self._buf = ""
        return cleaned

    def flush(self) -> str:
        out = _strip_dsml(self._buf)
        self._buf = ""
        return out


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

    user_chain: list[dict[str, Any]] = [
        m for m in clean if m["role"] != "system"
    ]
    chain: list[dict[str, Any]] = list(sys_msgs) + list(user_chain)

    try:
        yield _sse("status", {"phase": "planning"})
        used_tools = False
        early_answer: str | None = None
        collected_searches: list[tuple[str, list[dict[str, str]]]] = []

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
            native_tools = bool(msg.get("tool_calls"))
            tool_calls, prose = _normalize_assistant_tools(msg)

            if not tool_calls:
                if prose:
                    early_answer = prose
                break

            used_tools = True
            yield _sse("status", {"phase": "search"})

            # DeepSeek often emits tools as DSML text. Keep those off the
            # OpenAI tool_calls protocol so the model can leave tool-mode later.
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
                    {
                        "role": "assistant",
                        "content": prose or "(web_search)",
                    }
                )

            result_blobs: list[str] = []
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
                        collected_searches.append((query, results))
                    except Exception as exc:
                        yield _sse(
                            "error", {"message": f"web_search failed: {exc}"}
                        )
                        return
                yield _sse(
                    "tool",
                    {"name": "web_search", "query": query, "results": results},
                )
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
                            "web_search 결과:\n"
                            + "\n\n".join(result_blobs)
                            + "\n\n추가 검색이 필요하면 web_search를 다시 호출하고, "
                            "충분하면 최종 답변을 작성하세요."
                        ),
                    }
                )

        yield _sse("status", {"phase": "answer", "searched": used_tools})
        if early_answer is not None and not used_tools:
            step = 48
            for i in range(0, len(early_answer), step):
                yield _sse("delta", {"text": early_answer[i : i + step]})
        else:
            # Fresh text-only chain: prior tool_calls poison DeepSeek into
            # emitting more tool deltas with empty content.
            answer_chain: list[dict[str, Any]] = list(sys_msgs) + list(user_chain)
            if collected_searches:
                blocks = []
                for query, results in collected_searches:
                    blocks.append(
                        f"### web_search: {query}\n"
                        + json.dumps(results, ensure_ascii=False)
                    )
                answer_chain.append(
                    {
                        "role": "user",
                        "content": (
                            "아래는 방금 수행한 웹검색 결과입니다. "
                            "도구를 다시 호출하지 말고, 이 결과와 주어진 컨텍스트만으로 "
                            "최종 답변을 한국어로 작성하세요.\n\n"
                            + "\n\n".join(blocks)
                        ),
                    }
                )
            elif early_answer:
                # Had prose after tools somehow — still prefer rewrite on clean chain.
                pass

            answer_text = ""
            filt = _DsmlStreamFilter()
            with _or_chat(
                answer_chain, model=use_model, tools=None, stream=True
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
                    safe = filt.feed(piece)
                    if safe:
                        answer_text += safe
                        yield _sse("delta", {"text": safe})
            tail = filt.flush()
            if tail:
                answer_text += tail
                yield _sse("delta", {"text": tail})

            if not answer_text.strip():
                # Non-stream fallback if the model only emitted tool deltas.
                with _or_chat(
                    answer_chain
                    + [
                        {
                            "role": "user",
                            "content": "도구 호출 없이 최종 답변 본문만 출력하세요.",
                        }
                    ],
                    model=use_model,
                    tools=None,
                    stream=False,
                ) as resp:
                    data = json.loads(resp.read().decode())
                if data.get("error"):
                    yield _sse(
                        "error",
                        {
                            "message": json.dumps(
                                data["error"], ensure_ascii=False
                            )
                        },
                    )
                    return
                msg = ((data.get("choices") or [{}])[0].get("message") or {})
                fallback = _strip_dsml(str(msg.get("content") or "")).strip()
                if not fallback:
                    yield _sse(
                        "error",
                        {"message": "model returned empty answer after search"},
                    )
                    return
                step = 48
                for i in range(0, len(fallback), step):
                    yield _sse("delta", {"text": fallback[i : i + step]})

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
