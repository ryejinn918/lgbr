"""Signed PDF file GET — same path safety as lgbr-api."""

from __future__ import annotations

from pathlib import Path

from lgbr_api.reports import lookup_report_file
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from lgbr_mcp.signed_urls import verify_report_signature


async def serve_report_pdf(request: Request) -> Response:
    report_id = str(request.path_params.get("report_id") or "").strip()
    exp = request.query_params.get("exp")
    sig = request.query_params.get("sig")
    if not verify_report_signature(report_id, exp, sig):
        return JSONResponse(
            {"ok": False, "message": "invalid or expired signature"},
            status_code=403,
        )

    looked = lookup_report_file(report_id)
    if not looked.get("ok"):
        return JSONResponse(
            {"ok": False, "message": looked.get("message") or "error"},
            status_code=int(looked.get("status") or 404),
        )

    path = looked["path"]
    assert isinstance(path, Path)
    name = str(looked.get("file_name") or path.name)
    return FileResponse(
        path,
        filename=name,
        media_type="application/pdf",
    )
