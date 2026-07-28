import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
} from 'react'
import ForceGraph2D from 'react-force-graph-2d'

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

type SimNode = GraphNode & {
  x?: number
  y?: number
  fx?: number | null
  fy?: number | null
}

type SimLink = {
  source: string | SimNode
  target: string | SimNode
  type: string
}

type FgApi = {
  d3Force?: (
    name: string,
  ) =>
    | { strength?: (n: number) => unknown; distance?: (n: number) => unknown }
    | undefined
  zoomToFit?: (ms?: number, padding?: number) => void
}

const COLORS = {
  axis: '#0f172a',
  axisFill: '#e2e8f0',
  claim: '#64748b',
  belongs: '#cbd5e1',
  deepens: '#2563eb',
  disagrees: '#dc2626',
}

const Graph = ForceGraph2D as unknown as ComponentType<Record<string, unknown>>

function wrapLabel(text: string, maxChars: number, maxLines: number): string[] {
  const t = text.trim()
  if (!t) return ['']
  const lines: string[] = []
  let rest = t
  while (rest && lines.length < maxLines) {
    if (rest.length <= maxChars) {
      lines.push(rest)
      break
    }
    let cut = maxChars
    const space = rest.lastIndexOf(' ', maxChars)
    if (space > maxChars * 0.45) cut = space
    const chunk = rest.slice(0, cut).trimEnd()
    rest = rest.slice(cut).trimStart()
    if (lines.length === maxLines - 1 && rest) {
      lines.push(`${chunk.slice(0, Math.max(maxChars - 1, 1))}…`)
      break
    }
    lines.push(chunk)
  }
  return lines
}

function axisShortLabel(label: string, index: number): string {
  const raw = label.trim()
  const head = raw.split(/[:：]/)[0]?.trim() || raw
  const body = head.length > 28 ? `${head.slice(0, 27)}…` : head
  return `축${index + 1} · ${body}`
}

export function PerspectiveGraph({
  data,
  title,
}: {
  data: PerspectiveGraphData | null | undefined
  title: string
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const fgRef = useRef<FgApi | null>(null)
  const [size, setSize] = useState({ width: 420, height: 420 })

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const apply = () => {
      const w = Math.max(el.clientWidth || 420, 240)
      setSize({ width: w, height: Math.max(400, Math.round(w * 0.72)) })
    }
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const graph = useMemo(() => {
    const rawNodes = data?.nodes || []
    const rawEdges = data?.edges || []
    const axes = rawNodes.filter((n) => n.type === 'axis')
    const claims = rawNodes.filter((n) => n.type !== 'axis')
    const axisIndex = new Map(axes.map((a, i) => [a.id, i]))
    const claimAxis = new Map<string, string>()
    for (const e of rawEdges) {
      if (e.type !== 'belongs') continue
      if (axisIndex.has(e.source)) claimAxis.set(e.target, e.source)
      else if (axisIndex.has(e.target)) claimAxis.set(e.source, e.target)
    }
    const w = 640
    const padX = 72
    const axisY = 36

    const nodes: SimNode[] = []
    axes.forEach((n, i) => {
      const t = axes.length === 1 ? 0.5 : i / Math.max(axes.length - 1, 1)
      const x = padX + t * (w - padX * 2)
      nodes.push({
        ...n,
        fx: x,
        fy: axisY,
        x,
        y: axisY,
      })
    })

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

    for (const [aid, list] of byAxis) {
      const ai = axisIndex.get(aid) ?? 0
      const ax = nodes.find((n) => n.id === aid)
      const cx =
        ax?.fx ??
        padX + (ai / Math.max(axes.length - 1, 1)) * (w - padX * 2)
      list.forEach((c, j) => {
        const col = j % 3
        const row = Math.floor(j / 3)
        nodes.push({
          ...c,
          x: cx + (col - 1) * 56,
          y: 110 + row * 52,
        })
      })
    }

    const idSet = new Set(nodes.map((n) => n.id))
    const links: SimLink[] = (data?.edges || [])
      .filter((e) => idSet.has(e.source) && idSet.has(e.target))
      .map((e) => ({
        source: e.source,
        target: e.target,
        type: e.type,
      }))

    const axisOrder = axes.map((a) => a.id)
    return { nodes, links, axisCount: axes.length, axisOrder }
  }, [data])

  useEffect(() => {
    const fg = fgRef.current
    if (!fg?.d3Force) return
    fg.d3Force('charge')?.strength?.(-180)
    fg.d3Force('link')?.distance?.(62)
  }, [graph])

  const onEngineStop = useCallback(() => {
    fgRef.current?.zoomToFit?.(400, 48)
  }, [])

  useEffect(() => {
    if (graph.nodes.length === 0) return
    const t = window.setTimeout(() => {
      fgRef.current?.zoomToFit?.(400, 48)
    }, 900)
    return () => window.clearTimeout(t)
  }, [graph, size.width, size.height])

  if (graph.nodes.length === 0) {
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
          루트 {graph.axisCount}축 · 노드 {graph.nodes.length}
        </p>
      </div>
      <div className="eval-graph-canvas" ref={wrapRef}>
        <Graph
          ref={fgRef}
          graphData={graph}
          width={size.width}
          height={size.height}
          backgroundColor="rgba(0,0,0,0)"
          nodeId="id"
          cooldownTicks={100}
          enableNodeDrag
          onEngineStop={onEngineStop}
          linkColor={(l: SimLink) =>
            COLORS[l.type as keyof typeof COLORS] || COLORS.belongs
          }
          linkWidth={(l: SimLink) => (l.type === 'belongs' ? 1.2 : 1.8)}
          linkDirectionalArrowLength={(l: SimLink) =>
            l.type === 'belongs' ? 0 : 5
          }
          linkDirectionalArrowRelPos={0.9}
          nodeCanvasObject={(
            node: SimNode,
            ctx: CanvasRenderingContext2D,
            globalScale: number,
          ) => {
            const x = node.x || 0
            const y = node.y || 0
            const isAxis = node.type === 'axis'

            if (isAxis) {
              const axisIdx = Math.max(0, graph.axisOrder.indexOf(node.id))
              const label = axisShortLabel(node.label || node.id, axisIdx)
              const lines = wrapLabel(label, 16, 2)
              const fontSize = Math.max(11 / globalScale, 3)
              ctx.font = `600 ${fontSize}px "IBM Plex Sans KR", "Noto Sans KR", sans-serif`
              const lineH = fontSize * 1.25
              const textW = Math.max(
                ...lines.map((ln) => ctx.measureText(ln).width),
                40,
              )
              const padX = 8 / globalScale
              const padY = 5 / globalScale
              const boxW = textW + padX * 2
              const boxH = lines.length * lineH + padY * 2
              const r = 6 / globalScale

              ctx.beginPath()
              const left = x - boxW / 2
              const top = y - boxH / 2
              ctx.moveTo(left + r, top)
              ctx.arcTo(left + boxW, top, left + boxW, top + boxH, r)
              ctx.arcTo(left + boxW, top + boxH, left, top + boxH, r)
              ctx.arcTo(left, top + boxH, left, top, r)
              ctx.arcTo(left, top, left + boxW, top, r)
              ctx.closePath()
              ctx.fillStyle = COLORS.axisFill
              ctx.fill()
              ctx.strokeStyle = COLORS.axis
              ctx.lineWidth = 1.5 / globalScale
              ctx.stroke()

              ctx.fillStyle = COLORS.axis
              ctx.textAlign = 'center'
              ctx.textBaseline = 'top'
              lines.forEach((ln, i) => {
                ctx.fillText(ln, x, top + padY + i * lineH)
              })
              return
            }

            const r = 5
            ctx.beginPath()
            ctx.arc(x, y, r, 0, 2 * Math.PI)
            ctx.fillStyle = COLORS.claim
            ctx.fill()

            if (globalScale > 1.05) {
              const lines = wrapLabel(node.label || '', 12, 2)
              const fontSize = Math.max(9 / globalScale, 2)
              ctx.font = `400 ${fontSize}px "IBM Plex Sans KR", "Noto Sans KR", sans-serif`
              ctx.fillStyle = '#334155'
              ctx.textAlign = 'center'
              ctx.textBaseline = 'top'
              lines.forEach((ln, i) => {
                ctx.fillText(ln, x, y + r + 2 + i * fontSize * 1.2)
              })
            }
          }}
          nodePointerAreaPaint={(
            node: SimNode,
            color: string,
            ctx: CanvasRenderingContext2D,
          ) => {
            ctx.fillStyle = color
            ctx.beginPath()
            if (node.type === 'axis') {
              ctx.rect((node.x || 0) - 48, (node.y || 0) - 18, 96, 36)
            } else {
              ctx.arc(node.x || 0, node.y || 0, 10, 0, 2 * Math.PI)
            }
            ctx.fill()
          }}
        />
      </div>
    </div>
  )
}
