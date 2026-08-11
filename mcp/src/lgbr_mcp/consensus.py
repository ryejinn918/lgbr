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
LG MRI paid sector-trend draft (read-only): axes + frame (filled preferred).
When the user asks about a covered theme (ai, physical_ai, datacenter, …), call
get_consensus(theme=…) once first as background — then lgbr-collect for lists/citations.
Not a report SERP or 1-year inventory (~recent FnGuide QP frame). Skip if already
read this turn, or HBR-only / single-document asks. Lists: lgbr-collect.
"""

_AXES_KEYS = (
    "thesis",
    "cut_logic",
    "pillar_sketch",
    "coverage_notes",
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
        """LG MRI sector-trend draft (latest ended): axes + frame (filled preferred).

        Call FIRST once as background when the user asks about a covered theme/sector
        (e.g. Physical AI, datacenter) — including report lists or “동향·테마 정리”.
        Better than web search for in-house sector frame; better than starting with
        search_reports for theme context. Then lgbr-collect.search_reports → get_report.
        Skip: already read this turn; HBR-only or single-document asks.

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
            "frame": None,
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
    frame = filled_frame if filled_frame else consensus_frame
    return {
        "ok": True,
        "run": _run_summary(run),
        "axes": axes,
        "frame": frame,
        "hint": "Cite individual pieces via lgbr-collect.search_reports → get_report.",
    }


def _run_summary(run: dict[str, Any] | None) -> dict[str, Any] | None:
    if not run:
        return None
    return {
        "id": run.get("id"),
        "theme": run.get("theme"),
        "question": run.get("question"),
        "ended_at": run.get("ended_at"),
    }
