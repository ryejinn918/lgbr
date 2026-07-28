"""Human-facing provenance labels (short footnotes) vs internal keys."""

from __future__ import annotations

import re

# Shared instruction for frame / fill / chat (and echoed in select).
HUMAN_CITE_RULE = (
    "When naming a report in human prose, use only card fields "
    "provider, short_title, and published_at "
    "(never report_id, title, slug, slice_id, UUID, paths, or hashes). "
    "Always lead with provider. If unambiguous, (provider) alone is fine. "
    "Otherwise (provider, short_title); add published_at when still needed: "
    "(provider, short_title, published_at). "
    "Do not cite short_title alone. Optional page suffix: …, N쪽)."
)

_PROVIDER_STRIP = (
    "투자증권",
    "증권",
    "자본",
    "금융투자",
)


def short_provider(provider: str | None) -> str:
    """Compact house name for footnotes, e.g. KB투자증권 → KB."""
    raw = " ".join(str(provider or "").split())
    if not raw:
        return ""
    s = raw
    for suffix in _PROVIDER_STRIP:
        if s.endswith(suffix) and len(s) > len(suffix):
            s = s[: -len(suffix)].strip()
            break
    return s or raw


def short_report_title(title: str | None, *, max_len: int = 28) -> str:
    """Short series/title for footnotes — no source_key digits glued on."""
    t = " ".join(str(title or "").split())
    if not t:
        return ""
    # Drop leading bracket tags like [산업]
    t = re.sub(r"^\[[^\]]+\]\s*", "", t)
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def format_published_at(published_at: object | None) -> str:
    """Normalize published_at for headers/footnotes (prefer YYYY-MM-DD)."""
    if published_at is None:
        return ""
    if hasattr(published_at, "date") and callable(published_at.date):
        try:
            return published_at.date().isoformat()
        except Exception:
            pass
    if hasattr(published_at, "isoformat"):
        try:
            raw = published_at.isoformat()
        except Exception:
            raw = str(published_at)
    else:
        raw = str(published_at)
    raw = raw.strip()
    if not raw:
        return ""
    if "T" in raw:
        return raw.split("T", 1)[0]
    return raw[:10] if len(raw) >= 10 and raw[4] == "-" else raw


def human_doc_header(
    *,
    provider: str | None,
    title: str | None,
    published_at: object | None = None,
    page_start: int | None = None,
    page_end: int | None = None,
) -> str:
    """Card/compress header line for the LLM (no slug)."""
    house = short_provider(provider) or "—"
    short = short_report_title(title) or "—"
    bits = [house, short]
    pub = format_published_at(published_at)
    if pub:
        bits.append(pub)
    if page_start is not None and page_end is not None:
        if page_start == page_end:
            bits.append(f"{page_start}쪽")
        else:
            bits.append(f"{page_start}–{page_end}쪽")
    return " | ".join(bits)


def footnote_label(
    *,
    provider: str | None,
    title: str | None,
    short_title: str | None = None,
    published_at: object | None = None,
) -> str:
    """Provider-first footnote; include published_at when provided."""
    house = short_provider(provider) or ""
    short = (short_title or "").strip() or short_report_title(title)
    pub = format_published_at(published_at)
    parts = [p for p in (house, short, pub) if p]
    if not parts:
        return "(보고서)"
    return "(" + ", ".join(parts) + ")"
