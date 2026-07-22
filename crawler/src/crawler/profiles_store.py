"""DB-backed SearchReport filter profiles (datacenter / ai)."""

from __future__ import annotations

from typing import Any

from crawler.db import connect

PROFILE_MODES = frozenset({"datacenter", "ai"})
PERIOD_MONTHS = frozenset({3, 6, 12})


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    sectors = row.get("sectors") or []
    if not isinstance(sectors, (list, tuple)):
        sectors = list(sectors)
    return {
        "mode": row["mode"],
        "keyword": row["keyword"],
        "sectors": list(sectors),
        "period_months": int(row["period_months"]),
        "page_min_label": row["page_min_label"],
        "updated_at": (
            row["updated_at"].isoformat() if row.get("updated_at") else None
        ),
    }


def list_profiles() -> list[dict[str, Any]]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT mode, keyword, sectors, period_months, page_min_label, updated_at
                FROM search_profiles
                ORDER BY mode
                """
            )
            return [_serialize(dict(r)) for r in cur.fetchall()]


def get_profile_row(mode: str) -> dict[str, Any] | None:
    if mode not in PROFILE_MODES:
        return None
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT mode, keyword, sectors, period_months, page_min_label, updated_at
                FROM search_profiles
                WHERE mode = %s
                """,
                (mode,),
            )
            row = cur.fetchone()
            return _serialize(dict(row)) if row else None


def update_profile(mode: str, fields: dict[str, Any]) -> dict[str, Any]:
    if mode not in PROFILE_MODES:
        raise ValueError(f"invalid profile mode: {mode}")

    allowed = ("keyword", "sectors", "period_months", "page_min_label")
    updates: dict[str, Any] = {}
    for key in allowed:
        if key not in fields:
            continue
        updates[key] = fields[key]

    if not updates:
        row = get_profile_row(mode)
        if row is None:
            raise LookupError(f"profile not found: {mode}")
        return row

    if "keyword" in updates:
        keyword = str(updates["keyword"] or "").strip()
        if not keyword:
            raise ValueError("keyword must not be empty")
        updates["keyword"] = keyword

    if "period_months" in updates:
        try:
            months = int(updates["period_months"])
        except (TypeError, ValueError) as exc:
            raise ValueError("period_months must be 3, 6, or 12") from exc
        if months not in PERIOD_MONTHS:
            raise ValueError("period_months must be 3, 6, or 12")
        updates["period_months"] = months

    if "page_min_label" in updates:
        label = str(updates["page_min_label"] or "").strip()
        if not label:
            raise ValueError("page_min_label must not be empty")
        updates["page_min_label"] = label

    if "sectors" in updates:
        raw = updates["sectors"]
        if raw is None:
            sectors: list[str] = []
        elif isinstance(raw, (list, tuple)):
            sectors = [str(s).strip() for s in raw if str(s).strip()]
        else:
            raise ValueError("sectors must be an array of strings")
        updates["sectors"] = sectors

    set_parts = [f"{col} = %s" for col in updates]
    set_parts.append("updated_at = now()")
    values = list(updates.values()) + [mode]

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE search_profiles
                SET {", ".join(set_parts)}
                WHERE mode = %s
                RETURNING mode, keyword, sectors, period_months, page_min_label, updated_at
                """,
                values,
            )
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"profile not found: {mode}")
        conn.commit()
        return _serialize(dict(row))
