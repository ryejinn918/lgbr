"""Sector consensus MCP tools (read-only) — primary get_consensus + drill-downs."""

from __future__ import annotations

from typing import Any

from lgbr_api.consensus_api import (
    get_current_run,
    get_latest_ended as fetch_latest_ended,
    get_outputs,
    get_run_doc_compress,
    get_run_docs,
    list_history,
    list_inputs,
)
from mcp.server import MCPServer
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings

from lgbr_mcp.formatting import dumps

CONSENSUS_INSTRUCTIONS = """\
LGBR 섹터 컨센서스(조회 전용). 잡 시작/축 승인/중지는 UI 전용 — 하지 마세요.

1차(기본): get_consensus(theme) — 최신 ended 런의 분석 축 + filled/consensus 프레임.
다른 시점 런이 필요하면 list_runs로 run_id를 고른 뒤 get_consensus(theme, run_id=...).

2차(드릴다운, 필요할 때만):
- list_run_docs → get_doc_compress(문헌 요약; 원문 아님)
- list_theme_inputs(후보 풀/커버리지)

원문 PDF는 lgbr-collect의 search_reports / get_report를 쓰세요.
"""

_AXES_KEYS = (
    "thesis",
    "cut_logic",
    "pillar_sketch",
    "coverage_notes",
    "until",
    "resume_from",
    "core_count",
    "bibliography_count",
    "quality_pass_count",
    "pool_count",
    "core_max",
)

_DOC_SLIM_KEYS = (
    "report_id",
    "title",
    "provider",
    "role",
    "select_why",
    "rank",
    "page_count",
    "has_compress",
    "quality_pass",
)


def build_consensus_server(
    *,
    auth: AuthSettings | None = None,
    token_verifier: TokenVerifier | None = None,
) -> MCPServer:
    kwargs: dict[str, Any] = {}
    if auth is not None:
        kwargs["auth"] = auth
        kwargs["token_verifier"] = token_verifier
    mcp = MCPServer(
        name="lgbr-consensus",
        title="LGBR 섹터 컨센서스",
        instructions=CONSENSUS_INSTRUCTIONS,
        **kwargs,
    )

    @mcp.tool()
    def get_consensus(theme: str = "ai", run_id: str | None = None) -> str:
        """섹터 컨센서스 기본 조회: 분석 축 + filled_frame + consensus_frame.

        run_id 없으면 테마 최신 ended 런. 있으면 런이 없으면 frames는 null.

        Args:
            theme: ai, datacenter, macroeconomy, physical_ai, appliance, display, automotive, petrochemical
            run_id: list_runs에서 고른 런 id(생략 시 최신 ended)
        """
        return dumps(_get_consensus(theme=theme, run_id=run_id))

    @mcp.tool()
    def list_runs(theme: str | None = None, limit: int = 10) -> str:
        """런 이력(드릴다운). 다른 시점 run_id를 고를 때 사용.

        Args:
            theme: 테마 필터(생략 시 전체)
            limit: 기본 10, 최대 100
        """
        result = list_history(limit=limit, theme=theme)
        items = [
            _run_summary(run)
            for run in (result.get("items") or [])
            if isinstance(run, dict)
        ]
        current = get_current_run(event_limit=0)
        return dumps(
            {
                "ok": result.get("ok", True),
                "theme": theme,
                "items": items,
                "current": {
                    "state": current.get("state"),
                    "label": current.get("label"),
                    "run": _run_summary(current["run"])
                    if current.get("run")
                    else None,
                },
                "hint": "특정 런을 보려면 get_consensus(theme, run_id=...)를 호출하세요.",
            }
        )

    @mcp.tool()
    def list_run_docs(run_id: str) -> str:
        """런 선정 문헌 슬림 목록(드릴다운). 본문/compress 없음.

        Args:
            run_id: get_consensus / list_runs의 run id
        """
        raw = get_run_docs(run_id)
        if not raw.get("ok"):
            return dumps(raw)
        items = []
        for doc in raw.get("items") or []:
            if not isinstance(doc, dict):
                continue
            items.append({k: doc.get(k) for k in _DOC_SLIM_KEYS})
        return dumps(
            {
                "ok": True,
                "run_id": raw.get("run_id") or run_id,
                "count": len(items),
                "items": items,
                "hint": (
                    "문헌 요약은 get_doc_compress(run_id, report_id). "
                    "원문은 lgbr-collect."
                ),
            }
        )

    @mcp.tool()
    def get_doc_compress(run_id: str, report_id: str) -> str:
        """문헌 하나 파이프라인 압축 요약(드릴다운). 원문 PDF 대체가 아님.

        Args:
            run_id: 컨센서스 런 id
            report_id: list_run_docs의 report_id
        """
        result = get_run_doc_compress(run_id, report_id)
        if result.get("ok"):
            result = {
                **result,
                "hint": (
                    "원문 검증이 필요하면 lgbr-collect에서 동일 report_id를 조회하세요."
                ),
            }
        return dumps(result)

    @mcp.tool()
    def list_theme_inputs(theme: str = "ai") -> str:
        """테마 후보 리포트 풀(드릴다운). 커버리지·선정 맥락용.

        Args:
            theme: 섹터 테마
        """
        return dumps(list_inputs(theme=theme))

    return mcp


def _get_consensus(*, theme: str, run_id: str | None) -> dict[str, Any]:
    if run_id:
        status = get_current_run(run_id=run_id, event_limit=0)
        run = status.get("run")
        if not run:
            return {"ok": False, "message": "run not found", "run_id": run_id}
        out = get_outputs(str(run["id"]))
        return _consensus_payload(
            run=run,
            filled_frame=out.get("filled_frame") if out.get("ok") else None,
            consensus_frame=out.get("consensus_frame") if out.get("ok") else None,
            message=None if out.get("ok") else out.get("message"),
        )

    latest = fetch_latest_ended(theme=theme)
    if not latest.get("ok") and latest.get("status") == 400:
        return {
            "ok": False,
            "message": latest.get("message") or "invalid theme",
            "theme": theme,
        }
    run = latest.get("run")
    if not run:
        return {
            "ok": True,
            "theme": theme,
            "run": None,
            "axes": None,
            "filled_frame": None,
            "consensus_frame": None,
            "message": f"no ended consensus run for theme={theme}",
            "hint": "list_runs로 이력을 확인하거나 다른 theme을 시도하세요.",
        }
    return _consensus_payload(
        run=run,
        filled_frame=latest.get("filled_frame"),
        consensus_frame=latest.get("consensus_frame"),
        message=None,
    )


def _consensus_payload(
    *,
    run: dict[str, Any],
    filled_frame: Any,
    consensus_frame: Any,
    message: str | None,
) -> dict[str, Any]:
    criteria = run.get("criteria") if isinstance(run.get("criteria"), dict) else {}
    axes = {k: criteria.get(k) for k in _AXES_KEYS}
    payload: dict[str, Any] = {
        "ok": True,
        "run": _run_summary(run),
        "axes": axes,
        "filled_frame": filled_frame,
        "consensus_frame": consensus_frame,
        "hint": (
            "근거 문헌이 필요하면 list_run_docs → get_doc_compress. "
            "다른 시점 런은 list_runs."
        ),
    }
    if message:
        payload["message"] = message
    return payload


def _run_summary(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not run:
        return None
    criteria = run.get("criteria") if isinstance(run.get("criteria"), dict) else {}
    return {
        "id": run.get("id"),
        "theme": run.get("theme"),
        "state": run.get("state"),
        "label": run.get("label"),
        "question": run.get("question"),
        "started_at": run.get("started_at"),
        "ended_at": run.get("ended_at"),
        "until": criteria.get("until"),
        "thesis": criteria.get("thesis"),
    }
