"""Set B — sector consensus MCP tools (read-only)."""

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
from lgbr_api.consensus_eval import get_eval as consensus_get_eval
from mcp.server import MCPServer
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings

from lgbr_mcp.formatting import dumps

CONSENSUS_INSTRUCTIONS = """\
LGBR 섹터 컨센서스 산출물(조회 전용). 잡 시작/축 승인/중지는 하지 마세요(UI 전용).
진입: theme으로 get_latest_ended 또는 list_runs → run_id로 frames/docs/axes.
원문 PDF 검증이 필요하면 lgbr-collect 커넥터의 search_reports / pdf_url을 사용하세요.
get_doc_compress는 파이프라인 요약이며 원문 대체가 아닙니다.
awaiting 상태에서는 축(criteria)과 inputs만 유효하고 frames는 비어 있을 수 있습니다.
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
    def get_latest_ended(theme: str = "ai") -> str:
        """테마별 최근 완료(ended) 런과 filled_frame·consensus_frame.

        Args:
            theme: ai, datacenter, macroeconomy, physical_ai, appliance, display, automotive, petrochemical
        """
        return dumps(fetch_latest_ended(theme=theme))

    @mcp.tool()
    def list_runs(theme: str | None = None, limit: int = 10) -> str:
        """최근 컨센서스 런 목록(상태·질문·criteria 요약).

        Args:
            theme: 테마 필터(생략 시 전체)
            limit: 기본 10, 최대 100
        """
        result = list_history(limit=limit, theme=theme)
        items = []
        for run in result.get("items") or []:
            if not isinstance(run, dict):
                continue
            items.append(_run_summary(run))
        # Also surface current open run if any
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
                    "can_start": current.get("can_start"),
                },
            }
        )

    @mcp.tool()
    def get_run_axes(run_id: str) -> str:
        """런의 분석 축(thesis, cut_logic, pillar_sketch 등 criteria). awaiting에서도 조회 가능.

        Args:
            run_id: list_runs / get_latest_ended의 run id
        """
        status = get_current_run(run_id=run_id, event_limit=0)
        run = status.get("run")
        if not run:
            return dumps(
                {"ok": False, "message": "run not found", "run_id": run_id}
            )
        criteria = run.get("criteria") if isinstance(run.get("criteria"), dict) else {}
        axes = {k: criteria.get(k) for k in _AXES_KEYS}
        return dumps(
            {
                "ok": True,
                "run_id": run.get("id"),
                "theme": run.get("theme"),
                "state": run.get("state"),
                "question": run.get("question"),
                "axes": axes,
                "hint": (
                    "state=awaiting이면 축 확인 대기입니다. "
                    "승인(continue)은 UI에서만 가능합니다."
                ),
            }
        )

    @mcp.tool()
    def get_frames(run_id: str) -> str:
        """런의 filled_frame(보고서)과 consensus_frame(골격) 마크다운.

        Args:
            run_id: 컨센서스 런 id
        """
        out = get_outputs(run_id)
        return dumps(
            {
                "ok": out.get("ok"),
                "message": out.get("message"),
                "run_id": run_id,
                "state": out.get("state"),
                "filled_frame": out.get("filled_frame"),
                "consensus_frame": out.get("consensus_frame"),
                "fill_plan": out.get("fill_plan"),
            }
        )

    @mcp.tool()
    def list_run_docs(run_id: str) -> str:
        """런에 선정된 문헌 메타(selected/fill_extra, select_why). 본문 없음.

        Args:
            run_id: 컨센서스 런 id
        """
        return dumps(get_run_docs(run_id))

    @mcp.tool()
    def get_doc_compress(run_id: str, report_id: str) -> str:
        """문헌별 파이프라인 압축 요약(compress_md). 원문 PDF 대체가 아닙니다.

        Args:
            run_id: 컨센서스 런 id
            report_id: list_run_docs의 report_id
        """
        result = get_run_doc_compress(run_id, report_id)
        if result.get("ok"):
            result = {
                **result,
                "hint": (
                    "원문 검증이 필요하면 lgbr-collect에서 동일 report_id의 "
                    "pdf_url을 여세요."
                ),
            }
        return dumps(result)

    @mcp.tool()
    def list_theme_inputs(theme: str = "ai") -> str:
        """테마 후보 리포트 풀(quality_pass, will_select 등). 축 대기 시 커버리지 맥락용.

        Args:
            theme: 섹터 테마
        """
        return dumps(list_inputs(theme=theme))

    @mcp.tool()
    def get_eval(run_id: str) -> str:
        """저장된 eval 결과(있을 때만). UI 내비에는 없을 수 있음.

        Args:
            run_id: ended 런 id
        """
        return dumps(consensus_get_eval(run_id))

    return mcp


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
        "pillar_sketch": criteria.get("pillar_sketch"),
    }
