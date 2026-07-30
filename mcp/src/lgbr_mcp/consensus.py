"""Sector consensus MCP — get_consensus only (industry-trend draft)."""

from __future__ import annotations

from typing import Any

from lgbr_api.consensus_api import get_latest_ended as fetch_latest_ended
from mcp.server import MCPServer
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings

from lgbr_mcp.formatting import dumps

CONSENSUS_INSTRUCTIONS = """\
LG경영연구원 섹터 산업 동향 초안(조회 전용).
get_consensus(theme) → axes(분석 축) + consensus_frame(골격) + filled_frame(보고서 초안).
원문·개별 보고서는 lgbr-collect.
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
    def get_consensus(theme: str = "ai") -> str:
        """섹터 동향 초안(최신 ended). filled_frame=보고서, consensus_frame=골격, axes=분석 축.

        Args:
            theme: ai, datacenter, macroeconomy, physical_ai, appliance, display, automotive, petrochemical
        """
        return dumps(_get_consensus(theme=theme))

    return mcp


def _get_consensus(*, theme: str) -> dict[str, Any]:
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
        }
    return _consensus_payload(
        run=run,
        filled_frame=latest.get("filled_frame"),
        consensus_frame=latest.get("consensus_frame"),
    )


def _consensus_payload(
    *,
    run: dict[str, Any],
    filled_frame: Any,
    consensus_frame: Any,
) -> dict[str, Any]:
    criteria = run.get("criteria") if isinstance(run.get("criteria"), dict) else {}
    axes = {k: criteria.get(k) for k in _AXES_KEYS}
    return {
        "ok": True,
        "run": _run_summary(run),
        "axes": axes,
        "filled_frame": filled_frame,
        "consensus_frame": consensus_frame,
        "hint": "원문·근거 리포트는 lgbr-collect.search_reports / get_report.",
    }


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
