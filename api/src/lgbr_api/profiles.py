"""SearchReport filter profile API (ai / physical_ai / …)."""

from __future__ import annotations

from typing import Any

from lgbr_api.db import connect

PROFILE_MODES = frozenset(
    {
        "ai",
        "datacenter",
        "physical_ai",
        "appliance",
        "display",
        "automotive",
        "petrochemical",
    }
)
PERIOD_MONTHS = frozenset({3, 6, 12})


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    keywords = row.get("keywords") or []
    if not isinstance(keywords, (list, tuple)):
        keywords = list(keywords)
    sectors = row.get("sectors") or []
    if not isinstance(sectors, (list, tuple)):
        sectors = list(sectors)
    return {
        "mode": row["mode"],
        "keywords": [str(k) for k in keywords],
        "sectors": list(sectors),
        "period_months": int(row["period_months"]),
        "page_min_label": row["page_min_label"],
        "updated_at": (
            row["updated_at"].isoformat() if row.get("updated_at") else None
        ),
    }


def list_profiles() -> dict[str, Any]:
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT mode, keywords, sectors, period_months,
                           page_min_label, updated_at
                    FROM search_profiles
                    ORDER BY mode
                    """
                )
                items = [_serialize(dict(r)) for r in cur.fetchall()]
        return {"ok": True, "items": items}
    except Exception as exc:
        return {
            "ok": False,
            "message": str(exc),
            "items": [],
            "status": 500,
        }


def get_profile(mode: str) -> dict[str, Any]:
    if mode not in PROFILE_MODES:
        return {
            "ok": False,
            "message": f"invalid mode: {mode}",
            "profile": None,
            "status": 400,
        }
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT mode, keywords, sectors, period_months,
                           page_min_label, updated_at
                    FROM search_profiles
                    WHERE mode = %s
                    """,
                    (mode,),
                )
                row = cur.fetchone()
        if row is None:
            return {
                "ok": False,
                "message": f"profile not found: {mode}",
                "profile": None,
                "status": 404,
            }
        return {"ok": True, "profile": _serialize(dict(row))}
    except Exception as exc:
        return {
            "ok": False,
            "message": str(exc),
            "profile": None,
            "status": 500,
        }


def update_profile(mode: str, fields: dict[str, Any]) -> dict[str, Any]:
    if mode not in PROFILE_MODES:
        return {
            "ok": False,
            "message": f"invalid mode: {mode}",
            "profile": None,
            "status": 400,
        }

    allowed = ("keywords", "sectors", "period_months", "page_min_label")
    updates: dict[str, Any] = {}
    for key in allowed:
        if key in fields:
            updates[key] = fields[key]

    if not updates:
        return get_profile(mode)

    if "keywords" in updates:
        raw = updates["keywords"]
        if isinstance(raw, str):
            keywords = [raw.strip()] if raw.strip() else []
        elif isinstance(raw, (list, tuple)):
            keywords = [str(k).strip() for k in raw if str(k).strip()]
        else:
            return {
                "ok": False,
                "message": "keywords must be an array of strings",
                "profile": None,
                "status": 400,
            }
        if not keywords:
            return {
                "ok": False,
                "message": "keywords must not be empty",
                "profile": None,
                "status": 400,
            }
        updates["keywords"] = keywords

    if "period_months" in updates:
        try:
            months = int(updates["period_months"])
        except (TypeError, ValueError):
            return {
                "ok": False,
                "message": "period_months must be 3, 6, or 12",
                "profile": None,
                "status": 400,
            }
        if months not in PERIOD_MONTHS:
            return {
                "ok": False,
                "message": "period_months must be 3, 6, or 12",
                "profile": None,
                "status": 400,
            }
        updates["period_months"] = months

    if "page_min_label" in updates:
        label = str(updates["page_min_label"] or "").strip()
        if not label:
            return {
                "ok": False,
                "message": "page_min_label must not be empty",
                "profile": None,
                "status": 400,
            }
        updates["page_min_label"] = label

    if "sectors" in updates:
        raw = updates["sectors"]
        if raw is None:
            sectors: list[str] = []
        elif isinstance(raw, (list, tuple)):
            sectors = [str(s).strip() for s in raw if str(s).strip()]
        else:
            return {
                "ok": False,
                "message": "sectors must be an array of strings",
                "profile": None,
                "status": 400,
            }
        updates["sectors"] = sectors

    set_parts = [f"{col} = %s" for col in updates]
    set_parts.append("updated_at = now()")
    values = list(updates.values()) + [mode]

    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE search_profiles
                    SET {", ".join(set_parts)}
                    WHERE mode = %s
                    RETURNING mode, keywords, sectors, period_months,
                              page_min_label, updated_at
                    """,
                    values,
                )
                row = cur.fetchone()
            conn.commit()
        if row is None:
            return {
                "ok": False,
                "message": f"profile not found: {mode}",
                "profile": None,
                "status": 404,
            }
        return {"ok": True, "profile": _serialize(dict(row))}
    except Exception as exc:
        return {
            "ok": False,
            "message": str(exc),
            "profile": None,
            "status": 500,
        }
