"""Unit tests for slice-addressed fill helpers (no LLM)."""

from __future__ import annotations

from consensus.fill import (
    extract_target_slots,
    open_slice_body,
    strip_pillar_slots_from_filled,
    strip_slot_sections,
)


LEGACY_FRAME = """# Consensus frame

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

NEW_FRAME = """# 컨센서스 골격

## Executive Summary
긴장 요약

## 주제별 Deep Dive

### 1. Construction
- 주제 역할: demand signal
- 선정 근거: GS 2.4GW
- 추후 보강:
  - GS건설 동해 AIDC 부지 확보 세부
  - SK-AWS 울산 DC 지분 구조

### 2. Power
- 주제 역할: onsite generation
- 추후 보강:
  - LCOE 역전 가능성

## 본문 재오픈 우선순위
1. something
"""


def test_extract_target_slots_legacy():
    slots = extract_target_slots(LEGACY_FRAME)
    assert "GS건설 동해 AIDC 부지 확보 세부" in slots
    assert "SK-AWS 울산 DC 지분 구조" in slots
    assert "LCOE 역전 가능성" in slots
    assert len(slots) == 3


def test_extract_target_slots_new_terms():
    slots = extract_target_slots(NEW_FRAME)
    assert "GS건설 동해 AIDC 부지 확보 세부" in slots
    assert "SK-AWS 울산 DC 지분 구조" in slots
    assert "LCOE 역전 가능성" in slots
    assert len(slots) == 3


def test_strip_slot_sections_legacy():
    cleaned = strip_slot_sections(LEGACY_FRAME)
    assert "Slots to fill later" not in cleaned
    assert "### 1. Construction" in cleaned
    assert "GS 2.4GW" in cleaned
    assert "Body re-open priority" in cleaned


def test_strip_slot_sections_new_terms():
    cleaned = strip_slot_sections(NEW_FRAME)
    assert "추후 보강" not in cleaned
    assert "### 1. Construction" in cleaned
    assert "GS 2.4GW" in cleaned
    assert "본문 재오픈 우선순위" in cleaned


def test_open_slice_body_passthrough_and_cap():
    short = "hello " * 10
    assert open_slice_body(short, cap=1000) == short
    long = "x" * 5000
    out = open_slice_body(long, cap=100)
    assert out.startswith("x" * 100)
    assert "truncated" in out
    assert len(out) < len(long)


def test_strip_pillar_slots_from_filled_keeps_still_empty():
    filled = """# 살 붙인 논지

## 주제별 Deep Dive
### 1. Construction
- **Claim**: done
- **추후 보강**:
  - should be removed

## 미충족 보강 (다른 출처로 미룸)
- real gap only

## 참고 보고서
- a
"""
    cleaned, did = strip_pillar_slots_from_filled(filled)
    assert did is True
    assert "추후 보강" not in cleaned
    assert "미충족 보강" in cleaned
    assert "real gap only" in cleaned


def test_strip_pillar_slots_legacy_still_empty():
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
    filled = """# 살 붙인 논지

## 주제별 Deep Dive
### 1. X
- **Evidence**: 4.65%

## 미충족 보강
- none
"""
    cleaned, did = strip_pillar_slots_from_filled(filled)
    assert did is False
    assert cleaned == filled
