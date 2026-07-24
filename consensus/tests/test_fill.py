"""Unit tests for slice-addressed fill helpers (no LLM)."""

from __future__ import annotations

from consensus.fill import (
    extract_target_slots,
    open_slice_body,
    strip_pillar_slots_from_filled,
    strip_slot_sections,
)


FRAME = """# Consensus frame

## Major pillars

### 1. Construction
- **Role of this pillar**: demand signal
- **Consensus**: GS 2.4GW
- **Slots to fill later**:
  - GS건설 동해 AIDC 부지 확보 세부
  - SK-AWS 울산 DC 지분 구조

### 2. Power
- **Role of this pillar**: onsite generation
- **Slots to fill later**:
  - LCOE 역전 가능성

## Body re-open priority (keywords)
1. something
"""


def test_extract_target_slots():
    slots = extract_target_slots(FRAME)
    assert "GS건설 동해 AIDC 부지 확보 세부" in slots
    assert "SK-AWS 울산 DC 지분 구조" in slots
    assert "LCOE 역전 가능성" in slots
    assert len(slots) == 3


def test_strip_slot_sections_removes_pillar_slots():
    cleaned = strip_slot_sections(FRAME)
    assert "Slots to fill later" not in cleaned
    assert "### 1. Construction" in cleaned
    assert "GS 2.4GW" in cleaned
    assert "Body re-open priority" in cleaned


def test_open_slice_body_passthrough_and_cap():
    short = "hello " * 10
    assert open_slice_body(short, cap=1000) == short
    long = "x" * 5000
    out = open_slice_body(long, cap=100)
    assert out.startswith("x" * 100)
    assert "truncated" in out
    assert len(out) < len(long)


def test_strip_pillar_slots_from_filled_keeps_still_empty():
    filled = """# Filled frame

## Pillar enrichment
### 1. Construction
- **Claim**: done
- **Slots to fill later**:
  - should be removed

## Still-empty slots (defer to web/other sources)
- real gap only

## Reference reports
- a
"""
    cleaned, did = strip_pillar_slots_from_filled(filled)
    assert did is True
    assert "**Slots to fill later**" not in cleaned
    assert "Still-empty slots" in cleaned
    assert "real gap only" in cleaned


def test_strip_pillar_slots_noop_when_clean():
    filled = """# Filled frame

## Pillar enrichment
### 1. X
- **Evidence**: 4.65%

## Still-empty slots
- none
"""
    cleaned, did = strip_pillar_slots_from_filled(filled)
    assert did is False
    assert cleaned == filled
