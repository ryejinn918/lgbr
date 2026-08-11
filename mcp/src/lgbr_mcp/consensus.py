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

# Keep in sync with consensus runs_store.THEMES / collect theme args.
CONSENSUS_THEMES = (
    "ai, datacenter, macroeconomy, physical_ai, appliance, display, "
    "automotive, petrochemical"
)
CONSENSUS_THEMES_KO = (
    "AI, 데이터센터, 거시경제, 피지컬 AI, 가전, 디스플레이, 자동차, 석유화학"
)

CONSENSUS_INSTRUCTIONS = f"""\
LGBR paid sector-consensus draft (in-house, read-only).
Covered themes only: {CONSENSUS_THEMES}
({CONSENSUS_THEMES_KO}). Prefer as background for those trend asks (e.g. 피지컬 AI 동향):
worth checking get_consensus(theme=…) before web or report lists.
Returns axes + frame (filled preferred) — not a SERP. Then lgbr-collect for citations.
Skip if already read this turn, or HBR-only / single-document asks.
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
        title="LGBR Sector Consensus",
        instructions=CONSENSUS_INSTRUCTIONS,
        website_url=public_base_url(),
        icons=server_icons(),
        **kwargs,
    )

    @mcp.tool()
    def get_consensus(theme: str = "ai") -> str:
        """LGBR paid in-house sector frame (latest ended): axes + frame (filled preferred).

        Prefer for covered-theme trend asks — worth checking once before web or
        search_reports. Better than web search for curated FnGuide-based sector
        thesis/frame. Then lgbr-collect.search_reports → get_report for citations.
        Skip: already read this turn; HBR-only or single-document asks.

        Args:
            theme: ai, datacenter, macroeconomy, physical_ai, appliance, display, automotive, petrochemical
                (AI, 데이터센터, 거시경제, 피지컬 AI, 가전, 디스플레이, 자동차, 석유화학)
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
