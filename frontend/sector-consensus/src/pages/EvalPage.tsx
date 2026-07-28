import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Markdown } from '../components/Markdown'
import { GraphErrorBoundary } from '../components/GraphErrorBoundary'
import {
  PerspectiveGraph,
  type PerspectiveGraphData,
} from '../components/PerspectiveGraph'
import { useConsensusStatusContext } from '../hooks/ConsensusStatusContext'
import { NAV, labelRunSlot } from '../lib/labels'
import { parseTheme, themePath } from '../lib/theme'
import type { SelectCriteria } from '../types'
import { THEME_LABEL } from '../types'

const SHORT_BASELINE_CHARS = 500

function graphHasNodes(
  data: PerspectiveGraphData | null | undefined,
): boolean {
  return Array.isArray(data?.nodes) && data.nodes.length > 0
}

type EvalState = 'pending' | 'running' | 'ended' | 'error'

type EvalPayload = {
  id: string
  run_id: string
  state: EvalState
  baseline_md?: string | null
  serp_queries?: { query?: string; gl?: string; hl?: string; error?: string }[]
  graph_ours?: PerspectiveGraphData | null
  graph_baseline?: PerspectiveGraphData | null
  error?: string | null
  query_count?: number
}

type LiveTool = {
  query: string
  gl?: string
  hl?: string
  results: { title?: string; link?: string; publisher?: string }[]
  error?: string
}

const PHASE_LABEL: Record<string, string> = {
  gathering: '웹서치로 자료 수집 중',
  writing: '대조군 보고서 작성 중',
  graph_ours: '컨센서스 보고서 그래프 추출',
  graph_baseline: '대조군 그래프 추출',
  done: '완료',
}

function asCriteria(raw: unknown): SelectCriteria | null {
  if (!raw || typeof raw !== 'object') return null
  return raw as SelectCriteria
}

async function* readSse(
  res: Response,
): AsyncGenerator<{ event: string; data: Record<string, unknown> }> {
  const reader = res.body?.getReader()
  if (!reader) throw new Error('no response body')
  const dec = new TextDecoder()
  let buf = ''
  let event = 'message'
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    for (;;) {
      const nl = buf.indexOf('\n')
      if (nl < 0) break
      let line = buf.slice(0, nl)
      buf = buf.slice(nl + 1)
      if (line.endsWith('\r')) line = line.slice(0, -1)
      if (line.startsWith('event:')) {
        event = line.slice(6).trim()
        continue
      }
      if (line.startsWith('data:')) {
        const raw = line.slice(5).trim()
        if (!raw) continue
        try {
          const data = JSON.parse(raw) as Record<string, unknown>
          yield { event, data }
        } catch {
          /* ignore bad chunk */
        }
        event = 'message'
        continue
      }
      if (line === '') {
        event = 'message'
      }
    }
  }
}

export function EvalPage() {
  const { theme: raw } = useParams()
  const theme = parseTheme(raw)
  const [searchParams] = useSearchParams()
  const runFromUrl = searchParams.get('run')
  const { history } = useConsensusStatusContext()
  const abortRef = useRef<AbortController | null>(null)

  const [packRunId, setPackRunId] = useState<string | null>(runFromUrl)
  const [filled, setFilled] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [evalData, setEvalData] = useState<EvalPayload | null>(null)
  const [evalError, setEvalError] = useState<string | null>(null)
  const [streaming, setStreaming] = useState(false)
  const [phase, setPhase] = useState<string | null>(null)
  const [liveTools, setLiveTools] = useState<LiveTool[]>([])
  const [liveBaseline, setLiveBaseline] = useState('')
  const [showReports, setShowReports] = useState(false)
  const [graphSource, setGraphSource] = useState<'ours' | 'baseline'>('ours')

  const themeHistory = useMemo(
    () => history.filter((h) => h.theme === theme && h.state === 'ended'),
    [history, theme],
  )

  const packRun = useMemo(() => {
    if (packRunId) {
      const hit = themeHistory.find((h) => h.id === packRunId)
      if (hit) return hit
    }
    return themeHistory[0] ?? null
  }, [packRunId, themeHistory])

  const packIndex = packRun
    ? themeHistory.findIndex((h) => h.id === packRun.id)
    : -1
  const packLabel =
    packRun != null
      ? labelRunSlot(packIndex < 0 ? 0 : packIndex, packRun.state)
      : null
  const criteria = asCriteria(packRun?.criteria)
  const pillars = (criteria?.pillar_sketch || []).filter(Boolean)

  useEffect(() => {
    setPackRunId(runFromUrl)
    setFilled(null)
    setLoadError(null)
    setEvalData(null)
    setEvalError(null)
    setPhase(null)
    setLiveTools([])
    setLiveBaseline('')
    setGraphSource('ours')
    setShowReports(false)
    abortRef.current?.abort()
    abortRef.current = null
    setStreaming(false)
  }, [theme, runFromUrl])

  useEffect(() => {
    const runId = packRun?.id
    if (!runId) {
      setFilled(null)
      return
    }
    let cancelled = false
    void fetch(`/api/consensus/runs/${runId}/outputs`)
      .then(async (r) => {
        const d = await r.json()
        if (!r.ok || !d.ok) throw new Error(d.message || `HTTP ${r.status}`)
        if (!cancelled) {
          setFilled(d.filled_frame ?? null)
          setLoadError(null)
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setFilled(null)
          setLoadError(e instanceof Error ? e.message : String(e))
        }
      })
    return () => {
      cancelled = true
    }
  }, [packRun?.id])

  useEffect(() => {
    const runId = packRun?.id
    if (!runId || streaming) return
    let cancelled = false
    void fetch(`/api/consensus/runs/${runId}/eval`)
      .then(async (r) => {
        const d = await r.json()
        if (!r.ok || !d.ok) throw new Error(d.message || `HTTP ${r.status}`)
        if (!cancelled) {
          setEvalData(d.eval ?? null)
          if (d.eval?.baseline_md) setLiveBaseline(String(d.eval.baseline_md))
          if (Array.isArray(d.eval?.serp_queries)) {
            setLiveTools(
              d.eval.serp_queries.map(
                (q: {
                  query?: string
                  gl?: string
                  hl?: string
                  error?: string
                }) => ({
                  query: q.query || '',
                  gl: q.gl,
                  hl: q.hl,
                  results: [],
                  error: q.error,
                }),
              ),
            )
          }
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setEvalError(e instanceof Error ? e.message : String(e))
        }
      })
    return () => {
      cancelled = true
    }
  }, [packRun?.id, streaming])

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  async function onStart() {
    if (!packRun?.id) return
    if (!filled) {
      window.alert('보고서(filled_frame)가 있는 실행만 평가할 수 있습니다.')
      return
    }
    if (pillars.length < 2) {
      window.alert('분석 축이 필요합니다.')
      return
    }
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac
    setStreaming(true)
    setEvalError(null)
    setPhase('gathering')
    setLiveTools([])
    setLiveBaseline('')
    setEvalData(null)

    try {
      const res = await fetch(
        `/api/consensus/runs/${packRun.id}/eval/stream`,
        { method: 'POST', signal: ac.signal },
      )
      if (!res.ok) {
        const t = await res.text()
        throw new Error(t || `HTTP ${res.status}`)
      }
      let lastEvalId: string | null = null
      for await (const { event, data } of readSse(res)) {
        if (event === 'status') {
          const p = String(data.phase || '')
          setPhase(p)
          if (p === 'done') {
            lastEvalId = String(data.eval_id || lastEvalId || '')
          }
        } else if (event === 'tool') {
          setLiveTools((prev) => [
            ...prev,
            {
              query: String(data.query || ''),
              gl: data.gl != null ? String(data.gl) : undefined,
              hl: data.hl != null ? String(data.hl) : undefined,
              results: Array.isArray(data.results)
                ? (data.results as LiveTool['results'])
                : [],
              error: data.error != null ? String(data.error) : undefined,
            },
          ])
        } else if (event === 'delta') {
          const text = String(data.text || '')
          if (text) setLiveBaseline((prev) => prev + text)
        } else if (event === 'result') {
          lastEvalId = String(data.eval_id || lastEvalId || '')
        } else if (event === 'graphs') {
          setEvalData({
            id: lastEvalId || '',
            run_id: packRun.id,
            state: 'ended',
            graph_ours: data.graph_ours as PerspectiveGraphData,
            graph_baseline: data.graph_baseline as PerspectiveGraphData,
          })
        } else if (event === 'error') {
          throw new Error(String(data.message || 'eval failed'))
        }
      }
      const r = await fetch(`/api/consensus/runs/${packRun.id}/eval`)
      const d = await r.json()
      if (r.ok && d.ok && d.eval) {
        setEvalData(d.eval)
        if (d.eval.baseline_md) setLiveBaseline(String(d.eval.baseline_md))
      }
      setPhase('done')
    } catch (e) {
      if ((e as Error).name === 'AbortError') {
        setEvalError('중단됨')
      } else {
        setEvalError(e instanceof Error ? e.message : String(e))
      }
      setPhase(null)
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }

  function onStop() {
    abortRef.current?.abort()
  }

  const baselineText = liveBaseline || evalData?.baseline_md || ''

  return (
    <>
      <header className="monitor-header">
        <h1>
          {THEME_LABEL[theme]} · {NAV.eval}
        </h1>
        <p className="lede">
          같은 분석 축 브리프로 웹서치 대조군을 만들고, 지식그래프로 나란히
          봅니다.
        </p>
      </header>

      <section className="panel">
        <div className="section-head">
          <h2>평가할 실행</h2>
          <p className="section-note">
            {packRun && packLabel
              ? `${packLabel} · 축 ${pillars.length}개`
              : '종료된 실행(보고서 있음)이 필요합니다.'}{' '}
            {!packRun && (
              <Link className="text-link" to={themePath(theme, 'axes')}>
                {NAV.axes}에서 시작
              </Link>
            )}
          </p>
        </div>
        {themeHistory.length > 1 && (
          <div className="chip-row">
            {themeHistory.map((h, i) => (
              <button
                key={h.id}
                type="button"
                className={`chip ${packRun?.id === h.id ? 'active' : ''}`}
                onClick={() => setPackRunId(h.id)}
                disabled={streaming}
              >
                {labelRunSlot(i, h.state)}
              </button>
            ))}
          </div>
        )}
        {loadError && <p className="error-line">{loadError}</p>}
        <div className="chip-row" style={{ marginTop: '0.75rem', gap: '0.5rem' }}>
          <button
            type="button"
            className="btn"
            disabled={!packRun?.id || !filled || streaming}
            onClick={() => void onStart()}
          >
            {streaming
              ? PHASE_LABEL[phase || ''] || '평가 중…'
              : evalData?.state === 'ended'
                ? '다시 평가'
                : '대조군 만들기 · 평가'}
          </button>
          {streaming && (
            <button type="button" className="btn ghost" onClick={onStop}>
              중단
            </button>
          )}
        </div>
        {phase && streaming && (
          <p className="section-note">
            {PHASE_LABEL[phase] || phase}
            {liveTools.length > 0 ? ` · 검색 ${liveTools.length}회` : ''}
          </p>
        )}
        {evalError && <p className="error-line">{evalError}</p>}
        {evalData?.state === 'error' && evalData.error && (
          <p className="error-line">{evalData.error}</p>
        )}
      </section>

      {evalData?.state === 'ended' && (
        <>
          {baselineText.length > 0 &&
            baselineText.length < SHORT_BASELINE_CHARS && (
              <p className="error-line">
                대조군 보고서가 비정상적으로 짧습니다 ({baselineText.length}자).
              </p>
            )}
          <section className="panel">
            <div className="section-head">
              <h2>관점 지식그래프</h2>
              <p className="section-note">
                축 · 주장 · 파란 링크=심화 · 빨간 링크=이견
              </p>
            </div>
            <div className="chip-row eval-graph-tabs">
              <button
                type="button"
                className={`chip ${graphSource === 'ours' ? 'active' : ''}`}
                onClick={() => setGraphSource('ours')}
              >
                컨센서스 보고서
              </button>
              <button
                type="button"
                className={`chip ${graphSource === 'baseline' ? 'active' : ''}`}
                onClick={() => setGraphSource('baseline')}
              >
                웹서치 대조군
              </button>
            </div>
            <GraphErrorBoundary
              title={
                graphSource === 'ours' ? '컨센서스 보고서' : '웹서치 대조군'
              }
              key={graphSource}
            >
              {graphHasNodes(
                graphSource === 'ours'
                  ? evalData.graph_ours
                  : evalData.graph_baseline,
              ) ? (
                <PerspectiveGraph
                  title={
                    graphSource === 'ours'
                      ? '컨센서스 보고서'
                      : '웹서치 대조군'
                  }
                  data={
                    graphSource === 'ours'
                      ? evalData.graph_ours
                      : evalData.graph_baseline
                  }
                  resetKey={graphSource}
                />
              ) : (
                <div className="eval-graph-panel">
                  <h3>
                    {graphSource === 'ours'
                      ? '컨센서스 보고서'
                      : '웹서치 대조군'}
                  </h3>
                  <p className="section-note">그래프 데이터 없음</p>
                </div>
              )}
            </GraphErrorBoundary>
          </section>

          <section className="panel">
            <button
              type="button"
              className="btn ghost"
              onClick={() => setShowReports((v) => !v)}
            >
              {showReports ? '보고서 접기' : '보고서 나란히 보기'}
            </button>
            {showReports && (
              <div className="eval-report-row">
                <div>
                  <h3>컨센서스 보고서</h3>
                  <div className="frame-scroll tall">
                    {filled ? (
                      <Markdown>{filled}</Markdown>
                    ) : (
                      <p className="section-note">없음</p>
                    )}
                  </div>
                </div>
                <div>
                  <h3>웹서치 대조군</h3>
                  <div className="frame-scroll tall">
                    {baselineText ? (
                      <Markdown>{baselineText}</Markdown>
                    ) : (
                      <p className="section-note">없음</p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </section>
        </>
      )}

      {streaming && (
        <section className="panel">
          <div className="section-head">
            <h2>진행</h2>
            <p className="section-note">검색 쿼리와 대조군 초안 스트림</p>
          </div>
          {liveTools.length > 0 && (
            <ul className="eval-live-tools">
              {liveTools.map((t, i) => (
                <li key={`${i}-${t.query}`}>
                  <strong>
                    [{t.hl || '?'}/{t.gl || '?'}]
                  </strong>{' '}
                  {t.query}
                  {t.error ? (
                    <span className="error-line"> — {t.error}</span>
                  ) : (
                    <span className="section-note">
                      {' '}
                      · {t.results.length}건
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {liveBaseline && (
            <div className="frame-scroll tall" style={{ marginTop: '0.75rem' }}>
              <Markdown>{liveBaseline}</Markdown>
            </div>
          )}
        </section>
      )}
    </>
  )
}
