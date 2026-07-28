"""Slice max-char enforcement (TOC oversized → page split, no drop)."""

from __future__ import annotations

from consensus.compress import _truncate
from consensus.corpus import (
    SLICE_MAX_CHARS,
    enforce_slice_max,
    slices_from_toc,
)


def _fake_corpus(
    page_chars: list[int],
) -> dict:
    """Build a minimal page_corpus with given per-page body lengths."""
    pages = []
    parts: list[str] = []
    cursor = 0
    for i, n in enumerate(page_chars, start=1):
        marker = f"\n\n<<<PAGE {i}>>>\n"
        body = "x" * n
        block = marker + body
        start = cursor
        end = cursor + len(block)
        pages.append(
            {
                "page": i,
                "char_start": start,
                "char_end": end,
                "char_len": len(block),
                "text_sha256": "0" * 64,
            }
        )
        parts.append(block)
        cursor = end
    corpus = "".join(parts)
    return {
        "source_pdf": "/tmp/fake.pdf",
        "total_pdf_pages": len(page_chars),
        "corpus_char_len": len(corpus),
        "corpus_sha256": "0" * 64,
        "pages": pages,
        "corpus": corpus,
    }


def test_oversized_toc_section_split_under_max():
    # 9 pages × ~4k body ≈ 30k+ for one TOC section (like 1099901 s05).
    page_chars = [4000] * 9
    corp = _fake_corpus(page_chars)
    toc = {
        "toc_found": True,
        "top_level_ranges": [
            {
                "title": "05 Company analysis",
                "start_pdf_page": 1,
                "end_pdf_page": 9,
            }
        ],
    }
    slices, split_count = slices_from_toc(corp, toc)
    assert split_count >= 1
    assert all(s["char_len"] <= SLICE_MAX_CHARS for s in slices)
    # Full coverage, nothing dropped.
    assert slices[0]["page_start"] == 1
    assert slices[-1]["page_end"] == 9
    for a, b in zip(slices, slices[1:]):
        assert a["page_end"] + 1 == b["page_start"]
    # Flat sNN ids after split.
    ids = [s["slice_id"] for s in slices]
    assert ids == [f"s{i:02d}" for i in range(1, len(slices) + 1)]
    assert all(s["title"] == "05 Company analysis" for s in slices)


def test_small_toc_slices_unchanged_ids():
    page_chars = [500] * 6
    corp = _fake_corpus(page_chars)
    toc = {
        "toc_found": True,
        "top_level_ranges": [
            {"title": "A", "start_pdf_page": 1, "end_pdf_page": 2},
            {"title": "B", "start_pdf_page": 3, "end_pdf_page": 6},
        ],
    }
    slices, split_count = slices_from_toc(corp, toc)
    assert split_count == 0
    assert [s["slice_id"] for s in slices] == ["s01", "s02"]
    assert [s["title"] for s in slices] == ["A", "B"]
    assert all(s["char_len"] <= SLICE_MAX_CHARS for s in slices)


def test_front_matter_kept_when_split():
    # front p1 small; section p2-10 huge.
    page_chars = [200] + [5000] * 9
    corp = _fake_corpus(page_chars)
    toc = {
        "toc_found": True,
        "top_level_ranges": [
            {
                "title": "Big",
                "start_pdf_page": 2,
                "end_pdf_page": 10,
            }
        ],
    }
    slices, split_count = slices_from_toc(corp, toc)
    assert split_count >= 1
    assert slices[0]["slice_id"] == "front_matter"
    body = [s for s in slices if s["slice_id"] != "front_matter"]
    assert [s["slice_id"] for s in body] == [
        f"s{i:02d}" for i in range(1, len(body) + 1)
    ]
    assert all(s["char_len"] <= SLICE_MAX_CHARS for s in slices)


def test_enforce_covers_full_range():
    page_chars = [8000] * 5  # each page ~8k+marker; 2 pages may exceed 24k
    corp = _fake_corpus(page_chars)
    from consensus.corpus import slice_from_pages

    sl = slice_from_pages(corp, 1, 5)
    row = {
        "slice_id": "s01",
        "title": "X",
        "source": "toc",
        **{k: sl[k] for k in sl if k != "text"},
        "text": sl["text"],
    }
    assert row["char_len"] > SLICE_MAX_CHARS
    out, split_count = enforce_slice_max(corp, [row])
    assert split_count >= 1
    joined_len = sum(s["char_len"] for s in out)
    assert joined_len == row["char_len"]


def test_truncate_default_matches_slice_max():
    text = "a" * (SLICE_MAX_CHARS + 1000)
    out = _truncate(text)
    assert len(out) < len(text)
    assert "...[truncated]..." in out
    # head + tail + marker roughly at max
    assert len(out) <= SLICE_MAX_CHARS + 40


def test_nested_company_toc_ranges_split_parallel():
    """Page-numbered nested stock entries become separate slices (no hard split)."""
    # p1-60 front-ish small; 61 section head; 62-69 / 70-77 / 78-80 companies
    page_chars = [100] * 80
    corp = _fake_corpus(page_chars)
    toc = {
        "toc_found": True,
        "toc_ranges": [
            {"title": "VII. 게임", "start_pdf_page": 49, "level": 1},
            {"title": "기업분석", "start_pdf_page": 61, "level": 1},
            {"title": "NAVER (035420)", "start_pdf_page": 62, "level": 2},
            {"title": "카카오 (035720)", "start_pdf_page": 70, "level": 2},
            {"title": "NHN (181710)", "start_pdf_page": 78, "level": 2},
        ],
    }
    slices, split_count = slices_from_toc(corp, toc)
    assert split_count == 0
    body = [s for s in slices if s["slice_id"] != "front_matter"]
    titles = [s["title"] for s in body]
    assert "NAVER (035420)" in titles
    assert "카카오 (035720)" in titles
    assert "NHN (181710)" in titles
    naver = next(s for s in body if s["title"].startswith("NAVER"))
    kakao = next(s for s in body if s["title"].startswith("카카오"))
    nhn = next(s for s in body if s["title"].startswith("NHN"))
    assert naver["page_start"] == 62 and naver["page_end"] == 69
    assert kakao["page_start"] == 70 and kakao["page_end"] == 77
    assert nhn["page_start"] == 78 and nhn["page_end"] == 80
    assert all(s["char_len"] <= SLICE_MAX_CHARS for s in slices)


def test_same_start_page_keeps_last_title():
    page_chars = [200] * 10
    corp = _fake_corpus(page_chars)
    toc = {
        "toc_found": True,
        "toc_ranges": [
            {"title": "기업분석", "start_pdf_page": 5},
            {"title": "NAVER", "start_pdf_page": 5},  # same page → keep last
            {"title": "카카오", "start_pdf_page": 8},
        ],
    }
    slices, split_count = slices_from_toc(corp, toc)
    assert split_count == 0
    body = [s for s in slices if s["slice_id"] != "front_matter"]
    assert [s["title"] for s in body] == ["NAVER", "카카오"]
    assert body[0]["page_start"] == 5 and body[0]["page_end"] == 7


def test_top_level_ranges_fallback_still_works():
    """Legacy key without toc_ranges."""
    page_chars = [300] * 4
    corp = _fake_corpus(page_chars)
    toc = {
        "toc_found": True,
        "top_level_ranges": [
            {"title": "OnlyTop", "start_pdf_page": 1, "end_pdf_page": 4},
        ],
    }
    slices, split_count = slices_from_toc(corp, toc)
    assert split_count == 0
    assert len(slices) == 1
    assert slices[0]["title"] == "OnlyTop"


def test_page_less_nested_stays_one_section_then_hard_split():
    """TOC lists only parent with pages (children omitted) → one big slice → hard cap."""
    page_chars = [4000] * 9
    corp = _fake_corpus(page_chars)
    toc = {
        "toc_found": True,
        "toc_ranges": [
            {
                "title": "05 Company analysis",
                "start_pdf_page": 1,
                "end_pdf_page": 9,
                "level": 1,
            },
            # Nested without pages would not appear in toc_ranges at all.
        ],
    }
    slices, split_count = slices_from_toc(corp, toc)
    assert split_count >= 1
    assert all(s["title"] == "05 Company analysis" for s in slices)
    assert all(s["char_len"] <= SLICE_MAX_CHARS for s in slices)


def test_extract_ranges_prefers_toc_ranges():
    from consensus.toc import _extract_ranges

    data = {
        "toc_ranges": [{"title": "A", "start_pdf_page": 2}],
        "top_level_ranges": [{"title": "Legacy", "start_pdf_page": 1}],
    }
    out = _extract_ranges(data)
    assert len(out) == 1 and out[0]["title"] == "A"

    legacy_only = {
        "top_level_ranges": [{"title": "Legacy", "start_pdf_page": 1, "level": 1}],
    }
    out2 = _extract_ranges(legacy_only)
    assert out2[0]["title"] == "Legacy" and out2[0]["level"] == 1
