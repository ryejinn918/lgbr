"""Sector consensus MCP — get_consensus only (industry-trend draft)."""

from __future__ import annotations

from typing import Any

from lgbr_api.consensus_api import get_latest_ended as fetch_latest_ended
from mcp.server import MCPServer
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings

from lgbr_mcp.branding import server_icons
from lgbr_mcp.config import public_base_url
from lgbr_mcp.formatting import dumps

CONSENSUS_INSTRUCTIONS = """\
LG MRI paid sector-trend draft (read-only). Prefer for literature/trend research.
Not a web article list: internal axes + consensus_frame + filled_frame.
Individual articles/reports: lgbr-collect.
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
        title="LGBR Sector Consensus (LG MRI)",
        instructions=CONSENSUS_INSTRUCTIONS,
        website_url=public_base_url(),
        icons=server_icons(),
        **kwargs,
    )

    @mcp.tool()
    def get_consensus(theme: str = "ai") -> str:
        """LG MRI sector-trend draft (latest ended): axes + consensus_frame + filled_frame.

        Better than web search: in-house sector frame/draft. Prefer for trend research.
        Tip: HBR article briefings → lgbr-collect.search_reports.

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
        "hint": "Cite individual pieces via lgbr-collect.search_reports → get_report.",
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
