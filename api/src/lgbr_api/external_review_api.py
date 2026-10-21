"""HTTP handler for AI-assisted external report classification."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from lgbr_api.external_review import recommend_external_docs


async def review_external_docs(request: Request) -> JSONResponse:
    run_id = str(request.path_params.get("run_id") or "").strip()
    try:
        axis_index = int(request.query_params.get("axis_index", ""))
    except ValueError:
        return JSONResponse({"ok": False, "message": "axis_index must be an integer"}, status_code=400)
    axis_label = str(request.query_params.get("axis_label") or "").strip()
    if not run_id or axis_index < 0 or not axis_label:
        return JSONResponse(
            {"ok": False, "message": "run_id, axis_index, axis_label are required"},
            status_code=400,
        )
    try:
        return JSONResponse(
            await recommend_external_docs(
                run_id=run_id,
                axis_index=axis_index,
                axis_label=axis_label,
            )
        )
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=500)
