"""Smoke: light frame/fill editorial tips stay in prompt source."""

from __future__ import annotations

from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "consensus"


def test_frame_prompt_has_light_tips():
    text = (_SRC / "frame.py").read_text(encoding="utf-8")
    assert "갈림 없음" in text
    assert "단일 출처" in text
    assert "범위 밖 주제" in text
    assert "다시 넣지" in text or "back into that topic" in text


def test_fill_prompt_has_light_tips():
    text = (_SRC / "fill.py").read_text(encoding="utf-8")
    assert "2–3 mechanism branches" in text or "2-3 mechanism branches" in text
    assert "time-axis" in text or "time axis" in text
    assert "Watch" in text
    assert "never invent structure" in text
