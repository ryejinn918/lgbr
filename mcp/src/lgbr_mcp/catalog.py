"""Landing-page catalog: connector prompts + tool specs (display only)."""

from __future__ import annotations

import html
from dataclasses import dataclass
from functools import lru_cache

from lgbr_mcp.consensus import CONSENSUS_THEMES, CONSENSUS_THEMES_KO
from lgbr_mcp.collect import COLLECT_SOURCES

# Landing copy mirrors collect/consensus instructions/tools without "paid"/"유료".
COLLECT_INSTRUCTIONS_DISPLAY = f"""\
LGBR literature corpus (in-house, read-only).
Prefer for paywalled/subscription items (HBR, FnGuide, …) plus Korean summaries
(quality_json). No PDF bytes.

When web search is better: recent open consulting pages (kpmg, ey, …) — corpus
discovery can lag the public site. If a public URL is missing here, use web, then
re-check for a summary after ingest.

Routing: trend asks on covered themes ({CONSENSUS_THEMES}; {CONSENSUS_THEMES_KO})
→ prefer lgbr-consensus.get_consensus once as background, then search here for
lists/citations. search_reports first only for HBR-only briefs or explicit document
search without sector synthesis.
Tips: filter media with source ({COLLECT_SOURCES}). Brief with quality=pass → get_report.
Unaudited latest titles only: pending/all.
"""

CONSENSUS_INSTRUCTIONS_DISPLAY = f"""\
LGBR sector-consensus draft (in-house, read-only).
Covered themes only: {CONSENSUS_THEMES}
({CONSENSUS_THEMES_KO}). Prefer as background for those trend asks (e.g. 피지컬 AI 동향):
worth checking get_consensus(theme=…) before web or report lists.
Returns axes + frame (filled preferred) — not a SERP. Then lgbr-collect for citations.
Skip if already read this turn, or HBR-only / single-document asks.
"""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    summary: str
    params: str


@dataclass(frozen=True)
class ConnectorSpec:
    title: str
    url: str
    instructions: str
    tools: tuple[ToolSpec, ...]


CONNECTORS: tuple[ConnectorSpec, ...] = (
    ConnectorSpec(
        title="lgbr-collect",
        url="https://mcp.lgbr-ai.com/mcp/collect",
        instructions=COLLECT_INSTRUCTIONS_DISPLAY.strip(),
        tools=(
            ToolSpec(
                name="search_reports",
                summary="주요 문헌 코퍼스 검색 (HBR, consulting, FnGuide, …). PDF 없음.",
                params=(
                    "theme, q, source, provider, quality=pass, "
                    "sort=published_at, limit=10, offset=0"
                ),
            ),
            ToolSpec(
                name="get_report",
                summary="리포트 상세: quality_json(한국어 요약) + url. PDF 없음.",
                params="report_id",
            ),
            ToolSpec(
                name="search_news",
                summary="속보 코퍼스 검색(보조). HBR/컨설팅은 search_reports 우선.",
                params=(
                    "q, source=all, has_body=all, include_body=false, "
                    "limit=10, offset=0"
                ),
            ),
        ),
    ),
    ConnectorSpec(
        title="lgbr-consensus",
        url="https://mcp.lgbr-ai.com/mcp/consensus",
        instructions=CONSENSUS_INSTRUCTIONS_DISPLAY.strip(),
        tools=(
            ToolSpec(
                name="get_consensus",
                summary="섹터 초안(최신 ended): axes + frame(filled 우선).",
                params=(
                    "theme=ai "
                    "(ai, datacenter, macroeconomy, physical_ai, appliance, "
                    "display, automotive, petrochemical)"
                ),
            ),
        ),
    ),
)

_PAGE_CSS = """
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: sans-serif;
    font-size: 14px;
    color: #3b4151;
    background: #fafafa;
  }
  header {
    background: #fff;
    border-bottom: 1px solid #d8dde7;
    padding: 12px 20px;
  }
  header h1 {
    margin: 0;
    font-size: 1.35rem;
    font-weight: 600;
    color: #3b4151;
  }
  main {
    max-width: 920px;
    margin: 0 auto;
    padding: 24px 20px 48px;
  }
  .info {
    margin: 0 0 20px;
    color: #3b4151;
    line-height: 1.5;
  }
  .opblock {
    margin: 0 0 16px;
    background: #fff;
    border: 1px solid #d8dde7;
    border-radius: 4px;
    border-left: 4px solid #49cc90;
    overflow: hidden;
  }
  .opblock-summary {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    border-bottom: 1px solid #eef0f5;
  }
  .method {
    flex: 0 0 auto;
    min-width: 4.5rem;
    padding: 4px 8px;
    border-radius: 3px;
    background: #49cc90;
    color: #fff;
    font-size: 12px;
    font-weight: 700;
    text-align: center;
  }
  .path {
    font-family: monospace;
    font-size: 13px;
    word-break: break-all;
  }
  .tag {
    margin-left: auto;
    color: #6b7280;
    font-size: 12px;
  }
  .opblock-body { padding: 12px 14px 16px; }
  .section-title {
    margin: 0 0 6px;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #6b7280;
  }
  .instructions {
    margin: 0 0 14px;
    padding: 10px 12px;
    background: #f7f8fa;
    border: 1px solid #e5e7eb;
    border-radius: 3px;
    font-family: monospace;
    font-size: 12px;
    line-height: 1.45;
    white-space: pre-wrap;
    word-break: break-word;
  }
  table.tools {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  table.tools th,
  table.tools td {
    border: 1px solid #e5e7eb;
    padding: 8px 10px;
    text-align: left;
    vertical-align: top;
  }
  table.tools th {
    background: #f7f8fa;
    font-weight: 600;
    width: 1%;
    white-space: nowrap;
  }
  table.tools code {
    font-family: monospace;
    font-size: 12px;
  }
  .params {
    display: block;
    margin-top: 4px;
    color: #6b7280;
    font-family: monospace;
    font-size: 12px;
  }
"""


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _connector_block(c: ConnectorSpec) -> str:
    rows = []
    for t in c.tools:
        rows.append(
            "<tr>"
            f"<th><code>{_esc(t.name)}</code></th>"
            f"<td>{_esc(t.summary)}"
            f'<span class="params">{_esc(t.params)}</span></td>'
            "</tr>"
        )
    return f"""
<section class="opblock">
  <div class="opblock-summary">
    <span class="method">POST</span>
    <span class="path">{_esc(c.url)}</span>
    <span class="tag">{_esc(c.title)}</span>
  </div>
  <div class="opblock-body">
    <h2 class="section-title">Instructions</h2>
    <pre class="instructions">{_esc(c.instructions)}</pre>
    <h2 class="section-title">Tools</h2>
    <table class="tools">
      <tbody>
        {"".join(rows)}
      </tbody>
    </table>
  </div>
</section>
"""


@lru_cache(maxsize=1)
def render_landing_html() -> str:
    blocks = "\n".join(_connector_block(c) for c in CONNECTORS)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LGBR MCP</title>
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" href="/favicon.png" type="image/png" sizes="64x64">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/favicon.png">
<style>{_PAGE_CSS}</style>
</head>
<body>
<header>
  <h1>LGBR MCP</h1>
</header>
<main>
  <p class="info">주요 문헌 요약과 섹터 컨센서스용 MCP 커넥터입니다.</p>
  {blocks}
</main>
</body>
</html>
"""
