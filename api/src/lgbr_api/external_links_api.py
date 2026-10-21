"""HTTP handlers for Consensus-axis external evidence links.

The handlers are kept separate so the application route table can wire them
without mixing persistence validation into the main app module.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from lgbr_api.external_links import (
    list_candidates,
    list_links,
    remove_link,
    upsert_link,
)


def _error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "message": message}, status_code=status)


def _run_id(request: Request) -> str:
    return str(request.path_params.get("run_id") or "").strip()


async def external_candidates(request: Request) -> JSONResponse:
    run_id = _run_id(request)
    raw_axis = request.query_params.get("axis_index", "")
    try:
        axis_index = int(raw_axis)
    except ValueError:
        return _error("axis_index must be an integer")
    if not run_id or axis_index < 0:
        return _error("run_id and a non-negative axis_index are required")
    try:
        return JSONResponse(list_candidates(run_id=run_id, axis_index=axis_index))
    except Exception as exc:
        return _error(str(exc), 500)


async def external_links(request: Request) -> JSONResponse:
    run_id = _run_id(request)
    if not run_id:
        return _error("run_id is required")
    raw_axis = request.query_params.get("axis_index")
    axis_index: int | None = None
    if raw_axis is not None:
        try:
            axis_index = int(raw_axis)
        except ValueError:
            return _error("axis_index must be an integer")
    try:
        return JSONResponse(list_links(run_id=run_id, axis_index=axis_index))
    except Exception as exc:
        return _error(str(exc), 500)


async def save_external_link(request: Request) -> JSONResponse:
    run_id = _run_id(request)
    if not run_id:
        return _error("run_id is required")
    try:
        body: Any = await request.json()
    except Exception:
        return _error("request body must be JSON")
    if not isinstance(body, dict):
        return _error("request body must be an object")
    try:
        axis_index = int(body.get("axis_index"))
    except (TypeError, ValueError):
        return _error("axis_index must be an integer")
    axis_label = str(body.get("axis_label") or "").strip()
    report_id = str(body.get("report_id") or "").strip()
    relation = str(body.get("relation") or "").strip()
    if axis_index < 0 or not axis_label or not report_id or not relation:
        return _error("axis_index, axis_label, report_id, and relation are required")
    try:
        result = upsert_link(
            run_id=run_id,
            axis_index=axis_index,
            axis_label=axis_label,
            report_id=report_id,
            relation=relation,
            select_reason=str(body.get("select_reason") or "").strip() or None,
        )
        return JSONResponse(result, status_code=201)
    except ValueError as exc:
        return _error(str(exc))
    except Exception as exc:
        return _error(str(exc), 500)


async def delete_external_link(request: Request) -> JSONResponse:
    run_id = _run_id(request)
    raw_axis = request.query_params.get("axis_index", "")
    report_id = request.query_params.get("report_id", "").strip()
    try:
        axis_index = int(raw_axis)
    except ValueError:
        return _error("axis_index must be an integer")
    if not run_id or axis_index < 0 or not report_id:
        return _error("run_id, axis_index, and report_id are required")
    try:
        return JSONResponse(
            remove_link(run_id=run_id, axis_index=axis_index, report_id=report_id)
        )
    except Exception as exc:
        return _error(str(exc), 500)
