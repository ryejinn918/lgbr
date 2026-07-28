import { useEffect, useMemo, useState } from 'react'

export type GraphNode = {
  id: string
  type: string
  label: string
  quote?: string | null
  axis_id?: string | null
}

export type GraphEdge = {
  source: string
  target: string
  type: string
}

export type PerspectiveGraphData = {
  nodes?: GraphNode[]
  edges?: GraphEdge[]
  meta?: Record<string, unknown>
}

type ClaimRel = {
  type: 'deepens' | 'disagrees'
  targetId: string
  targetLabel: string
}

type AxisGroup = {
  axis: GraphNode
  axisIndex: number
  claims: { node: GraphNode; rels: ClaimRel[] }[]
}

function axisHeading(label: string, index: number): string {
  const raw = label.trim()
  const head = raw.split(/[:：]/)[0]?.trim() || raw
  return `축${index + 1} · ${head}`
}

function shortLabel(label: string, max = 36): string {
  const t = label.trim()
  if (t.length <= max) return t
  return `${t.slice(0, max - 1)}…`
}

function buildGroups(data: PerspectiveGraphData | null | undefined): {
  groups: AxisGroup[]
  byId: Map<string, GraphNode>
  axisCount: number
  nodeCount: number
} {
  const rawNodes = data?.nodes || []
  const rawEdges = data?.edges || []
  const byId = new Map(rawNodes.map((n) => [n.id, n]))
  const axes = rawNodes.filter((n) => n.type === 'axis')
  const claims = rawNodes.filter((n) => n.type !== 'axis')
  const axisIndex = new Map(axes.map((a, i) => [a.id, i]))

  const claimAxis = new Map<string, string>()
  for (const e of rawEdges) {
    if (e.type !== 'belongs') continue
    if (axisIndex.has(e.source)) claimAxis.set(e.target, e.source)
    else if (axisIndex.has(e.target)) claimAxis.set(e.source, e.target)
  }

  const relsByClaim = new Map<string, ClaimRel[]>()
  for (const e of rawEdges) {
    if (e.type !== 'deepens' && e.type !== 'disagrees') continue
    const target = byId.get(e.target)
    if (!target) continue
    const list = relsByClaim.get(e.source) || []
    list.push({
      type: e.type,
      targetId: e.target,
      targetLabel: target.label || e.target,
    })
    relsByClaim.set(e.source, list)
  }

  const byAxis = new Map<string, GraphNode[]>()
  for (const c of claims) {
    const fromEdge = claimAxis.get(c.id)
    const aid =
      fromEdge && axisIndex.has(fromEdge)
        ? fromEdge
        : c.axis_id && axisIndex.has(c.axis_id)
          ? c.axis_id
          : axes[0]?.id || '__none__'
    const list = byAxis.get(aid) || []
    list.push(c)
    byAxis.set(aid, list)
  }

  const groups: AxisGroup[] = axes.map((axis, i) => ({
    axis,
    axisIndex: i,
    claims: (byAxis.get(axis.id) || []).map((node) => ({
      node,
      rels: relsByClaim.get(node.id) || [],
    })),
  }))

  const orphanAid = '__none__'
  const orphans = byAxis.get(orphanAid)
  if (orphans?.length && !axisIndex.has(orphanAid)) {
    const orphanAxis: GraphNode = {
      id: orphanAid,
      type: 'axis',
      label: '미분류',
    }
    byId.set(orphanAid, orphanAxis)
    groups.push({
      axis: orphanAxis,
      axisIndex: axes.length,
      claims: orphans.map((node) => ({
        node,
        rels: relsByClaim.get(node.id) || [],
      })),
    })
  }

  return {
    groups,
    byId,
    axisCount: axes.length,
    nodeCount: rawNodes.length,
  }
}

export function PerspectiveGraph({
  data,
  title,
  resetKey,
}: {
  data: PerspectiveGraphData | null | undefined
  title: string
  /** Change to clear selection (e.g. when switching ours/baseline). */
  resetKey?: string
}) {
  const { groups, byId, axisCount, nodeCount } = useMemo(
    () => buildGroups(data),
    [data],
  )
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    setSelectedId(null)
  }, [resetKey, data])

  const selected = selectedId ? byId.get(selectedId) : undefined

  const selectedRels = useMemo(() => {
    if (!selected || selected.type === 'axis') return [] as ClaimRel[]
    const edges = data?.edges || []
    const out: ClaimRel[] = []
    for (const e of edges) {
      if (e.source !== selected.id) continue
      if (e.type !== 'deepens' && e.type !== 'disagrees') continue
      const target = byId.get(e.target)
      if (!target) continue
      out.push({
        type: e.type,
        targetId: e.target,
        targetLabel: target.label || e.target,
      })
    }
    return out
  }, [selected, data?.edges, byId])

  if (nodeCount === 0) {
    return (
      <div className="eval-graph-panel">
        <div className="section-head">
          <h3>{title}</h3>
          <p className="section-note">그래프 데이터 없음</p>
        </div>
      </div>
    )
  }

  return (
    <div className="eval-graph-panel">
      <div className="section-head">
        <h3>{title}</h3>
        <p className="section-note">
          루트 {axisCount}축 · 노드 {nodeCount}
        </p>
      </div>
      <div className="eval-graph-layout">
        <div className="eval-graph-outline">
          {groups.map((g) => (
            <section key={g.axis.id} className="eval-graph-axis">
              <button
                type="button"
                className={`eval-graph-axis-btn${
                  selectedId === g.axis.id ? ' is-selected' : ''
                }`}
                onClick={() => setSelectedId(g.axis.id)}
              >
                {axisHeading(g.axis.label || g.axis.id, g.axisIndex)}
              </button>
              <ul className="eval-graph-claims">
                {g.claims.map(({ node, rels }) => (
                  <li key={node.id}>
                    <button
                      type="button"
                      className={`eval-graph-claim-btn${
                        selectedId === node.id ? ' is-selected' : ''
                      }`}
                      title={node.label || node.id}
                      onClick={() => setSelectedId(node.id)}
                    >
                      <span className="eval-graph-claim-label">
                        {node.label || node.id}
                      </span>
                    </button>
                    {rels.length > 0 && (
                      <div className="eval-graph-rels">
                        {rels.map((r) => (
                          <button
                            key={`${r.type}-${r.targetId}`}
                            type="button"
                            className={`eval-graph-rel eval-graph-rel-${r.type}`}
                            onClick={() => setSelectedId(r.targetId)}
                          >
                            {r.type === 'deepens' ? '심화' : '이견'} →{' '}
                            {shortLabel(r.targetLabel, 28)}
                          </button>
                        ))}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <aside className="eval-graph-detail">
          {selected ? (
            <>
              <p className="eval-graph-detail-kind">
                {selected.type === 'axis' ? '분석 축' : '주장'}
              </p>
              <h4 className="eval-graph-detail-title">
                {selected.type === 'axis'
                  ? axisHeading(
                      selected.label || selected.id,
                      groups.find((g) => g.axis.id === selected.id)
                        ?.axisIndex ?? 0,
                    )
                  : selected.label || selected.id}
              </h4>
              {selected.type !== 'axis' && (
                <blockquote className="eval-graph-quote">
                  {selected.quote?.trim()
                    ? selected.quote.trim()
                    : '인용 없음'}
                </blockquote>
              )}
              {selected.type === 'axis' && selected.label && (
                <p className="eval-graph-detail-body">{selected.label}</p>
              )}
              {selectedRels.length > 0 && (
                <ul className="eval-graph-detail-rels">
                  {selectedRels.map((r) => (
                    <li key={`${r.type}-${r.targetId}`}>
                      <button
                        type="button"
                        className={`eval-graph-rel eval-graph-rel-${r.type}`}
                        onClick={() => setSelectedId(r.targetId)}
                      >
                        {r.type === 'deepens' ? '심화' : '이견'} →{' '}
                        {shortLabel(r.targetLabel, 40)}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="section-note">축 또는 주장을 선택하면 상세가 표시됩니다.</p>
          )}
        </aside>
      </div>
    </div>
  )
}
