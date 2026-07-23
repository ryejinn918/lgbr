"""OpenRouter chat (stream)."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from consensus.db import load_database_env

DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
_T0 = time.time()


def api_key() -> str:
    load_database_env()
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is required")
    return key


def log(msg: str) -> None:
    print(f"[{time.time() - _T0:6.1f}s] {msg}", flush=True)


def chat(
    messages: list[dict[str, Any]],
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    label: str = "chat",
    out_dir: Path | None = None,
) -> tuple[str, dict[str, Any] | None]:
    n = sum(len(str(m.get("content") or "")) for m in messages)
    log(f"{label}: start stream (prompt~{n:,} chars, model={model})")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
        "reasoning": {"effort": "none"},
        "provider": {"sort": "throughput"},
    }
    req = urllib.request.Request(
        DEFAULT_BASE_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/lgbr",
            "X-Title": "lgbr-consensus",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    t0 = time.time()
    parts: list[str] = []
    finish = None
    usage = None
    first = None
    partial = out_dir / f"_{label}_partial.md" if out_dir else None
    meta_path = out_dir / f"_{label}_stream.meta.json" if out_dir else None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(req, timeout=600) as resp:
        while True:
            line = resp.readline()
            if not line:
                break
            line = line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data_s = line[5:].strip()
            if data_s == "[DONE]":
                break
            try:
                chunk = json.loads(data_s)
            except json.JSONDecodeError:
                continue
            if chunk.get("error"):
                raise RuntimeError(json.dumps(chunk["error"], ensure_ascii=False))
            if chunk.get("usage"):
                usage = chunk["usage"]
            ch0 = (chunk.get("choices") or [{}])[0]
            if ch0.get("finish_reason"):
                finish = ch0["finish_reason"]
            piece = (ch0.get("delta") or {}).get("content") or ""
            if not piece:
                continue
            if first is None:
                first = time.time()
                log(f"{label}: first token {first - t0:.1f}s")
            parts.append(piece)
            if partial is not None:
                partial.write_text("".join(parts), encoding="utf-8")
    content = "".join(parts).strip()
    meta = {
        "label": label,
        "model": model,
        "elapsed_s": round(time.time() - t0, 2),
        "chars": len(content),
        "first_token_s": None if first is None else round(first - t0, 2),
        "finish_reason": finish,
        "usage": usage,
    }
    if meta_path is not None:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"{label}: done {meta['elapsed_s']}s out={len(content)} finish={finish}")
    if not content:
        raise RuntimeError(f"{label}: empty")
    if finish == "length":
        raise RuntimeError(f"{label}: truncated")
    return content, usage


def parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


def usage_tokens(usage: dict[str, Any] | None) -> tuple[int, int]:
    if not usage:
        return 0, 0
    tin = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    tout = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    return tin, tout
