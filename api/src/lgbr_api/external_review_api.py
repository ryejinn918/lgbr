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
        return JSONResponse(
            {
                "ok": False,
                "status": "failed",
                "message": "axis_index must be an integer",
            },
            status_code=400,
        )

    axis_label = str(request.query_params.get("axis_label") or "").strip()

    if not run_id or axis_index < 0 or not axis_label:
        return JSONResponse(
            {
                "ok": False,
                "status": "failed",
                "message": "run_id, axis_index, axis_label are required",
            },
            status_code=400,
        )

    try:
        result = await recommend_external_docs(
            run_id=run_id,
            axis_index=axis_index,
            axis_label=axis_label,
        )

        if not isinstance(result, dict):
            result = {"result": result}

        result.setdefault("ok", True)
        result.setdefault("status", "completed")

        if result.get("ok") is False:
            result["status"] = "failed"
        elif result.get("message") is None:
            result["message"] = (
                "외부 자료 분석이 완료되었습니다. "
                "추천 자료가 없으면 연결할 외부 자료가 없는 것입니다."
            )

        return JSONResponse(result)

    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "status": "failed",
                "message": (
                    "외부 자료 분석에 실패했습니다. "
                    "잠시 후 다시 시도해 주세요."
                ),
                "detail": str(exc),
            },
            status_code=500,
        )