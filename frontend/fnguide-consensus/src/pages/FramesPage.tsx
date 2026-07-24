import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Markdown } from '../components/Markdown'
import { formatTime } from '../lib/format'
import { FRAME_TAB, NAV, labelDocStatus } from '../lib/labels'
import type { ConsensusRun, ConsensusTheme } from '../types'
import { THEME_LABEL } from '../types'

type ViewTab = 'filled' | 'consensus' | 'materials'

type DocRow = {
  role: string
  rank: number | null
  doc_status: string
  report_id: string
  title: string
  provider?: string | null
  has_compress: boolean
  compress_md?: string | null
  slice_count?: number | null
  exclude_reason?: string | null
  select_why?: string | null
}

const THEMES: ConsensusTheme[] = ['datacenter', 'ai', 'physical_ai']

function parseTheme(raw: string | null): ConsensusTheme {
  if (raw && THEMES.includes(raw as ConsensusTheme)) return raw as ConsensusTheme
  return 'datacenter'
}

export function FramesPage() {
  const [params, setParams] = useSearchParams()
  const theme = parseTheme(params.get('theme'))
  const [run, setRun] = useState<ConsensusRun | null>(null)
  const [filled, setFilled] = useState<string | null>(null)
  const [consensus, setConsensus] = useState<string | null>(null)
  const [docs, setDocs] = useState<DocRow[]>([])
  const [tab, setTab] = useState<ViewTab>('filled')
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    setDocs([])
    setSelectedDocId(null)
    void fetch(`/api/consensus/latest?theme=${theme}`)
      .then(async (r) => {
        const d = await r.json()
        if (!r.ok || !d.ok) throw new Error(d.message || `HTTP ${r.status}`)
        if (cancelled) return
        const latestRun = (d.run as ConsensusRun | null) ?? null
        setRun(latestRun)
        setFilled(d.filled_frame ?? null)
        setConsensus(d.consensus_frame ?? null)
        if (!latestRun) return
        const docRes = await fetch(`/api/consensus/runs/${latestRun.id}/docs`)
        const docData = await docRes.json()
        if (!docRes.ok || !docData.ok) {
          throw new Error(docData.message || `docs HTTP ${docRes.status}`)
        }
        if (cancelled) return
        const items = (docData.items ?? []) as DocRow[]
        setDocs(items)
        const first = items.find((x) => x.has_compress) ?? items[0] ?? null
        setSelectedDocId(first?.report_id ?? null)
      })
      .catch((e) => {
        if (!cancelled) {
          setRun(null)
          setFilled(null)
          setConsensus(null)
          setDocs([])
          setError(e instanceof Error ? e.message : String(e))
        }
      })
    return () => {
      cancelled = true
    }
  }, [theme])

  const selectedDocs = useMemo(
    () =>
      docs.filter((d) => d.role === 'selected' || d.role === 'fill_extra'),
    [docs],
  )
  const selectedDoc =
    selectedDocs.find((d) => d.report_id === selectedDocId) ??
    selectedDocs[0] ??
    null

  const frameBody = tab === 'filled' ? filled : tab === 'consensus' ? consensus : null

  return (
    <>
      <header className="monitor-header">
        <h1>{NAV.frames}</h1>
        <p className="lede">
          섹터별 최신 논지와, 근거로 쓴 리포트 요약을 확인합니다.
        </p>
      </header>

      <section className="panel">
        <div className="chip-row">
          {THEMES.map((t) => (
            <button
              key={t}
              type="button"
              className={`chip ${theme === t ? 'active' : ''}`}
              onClick={() => {
                setParams({ theme: t }, { replace: true })
                setTab('filled')
              }}
            >
              {THEME_LABEL[t]}
            </button>
          ))}
        </div>
        {run ? (
          <p className="section-note">
            {run.asset_id} · {formatTime(run.ended_at)} · {run.question}
          </p>
        ) : (
          <p className="section-note">
            이 섹터에 완료된 실행이 없습니다.{' '}
            <Link to={`/ops?theme=${theme}`}>{NAV.ops}에서 생성</Link>
          </p>
        )}
        <Link className="btn" to={`/?theme=${theme}`}>
          이 섹터로 {NAV.compare}
        </Link>
        {error && <p className="error-line">{error}</p>}
      </section>

      <section className="panel">
        <div className="chip-row">
          {(
            [
              ['filled', FRAME_TAB.filled],
              ['consensus', FRAME_TAB.consensus],
              ['materials', FRAME_TAB.materials],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              type="button"
              className={`chip ${tab === k ? 'active' : ''}`}
              onClick={() => setTab(k)}
            >
              {label}
            </button>
          ))}
        </div>
        {tab === 'filled' && (
          <p className="section-note">
            골격에 근거·수치를 채운 본문입니다. 비교 시 기본으로 참고합니다.
          </p>
        )}
        {tab === 'consensus' && (
          <p className="section-note">
            여러 리포트가 수렴한 총론·핵심 축 수준의 골격입니다.
          </p>
        )}
        {tab === 'materials' && (
          <p className="section-note">
            이번 실행에 선정된 증권사 리포트와 문서별 요약입니다.
          </p>
        )}

        {tab !== 'materials' &&
          (frameBody ? (
            <div className="frame-scroll tall">
              <Markdown>{frameBody}</Markdown>
            </div>
          ) : (
            <p className="section-note">표시할 논지가 없습니다.</p>
          ))}

        {tab === 'materials' && (
          <div className="materials-layout">
            <ul className="materials-list">
              {selectedDocs.length === 0 && (
                <li className="section-note">선정 리포트 없음</li>
              )}
              {selectedDocs.map((d) => (
                <li key={d.report_id}>
                  <button
                    type="button"
                    className={`materials-item ${
                      selectedDoc?.report_id === d.report_id ? 'active' : ''
                    }`}
                    onClick={() => setSelectedDocId(d.report_id)}
                  >
                    <span className="materials-title">{d.title}</span>
                    <span className="section-note">
                      {d.role === 'fill_extra' ? '참고 · ' : '골격 · '}
                      {d.provider ?? '—'} · {labelDocStatus(d.doc_status)}
                      {d.has_compress ? '' : ' · 요약 없음'}
                    </span>
                    {d.select_why ? (
                      <span className="section-note materials-why">
                        {d.select_why}
                      </span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
            <div className="materials-body">
              {selectedDoc ? (
                <>
                  <p className="section-note">
                    {selectedDoc.title}
                    {selectedDoc.slice_count != null
                      ? ` · 요약 구간 ${selectedDoc.slice_count}개`
                      : ''}
                  </p>
                  {selectedDoc.select_why ? (
                    <p className="select-review-body">{selectedDoc.select_why}</p>
                  ) : null}
                  {selectedDoc.has_compress && selectedDoc.compress_md ? (
                    <div className="frame-scroll tall">
                      <Markdown>{selectedDoc.compress_md}</Markdown>
                    </div>
                  ) : (
                    <p className="section-note">이 리포트의 요약이 없습니다.</p>
                  )}
                </>
              ) : (
                <p className="section-note">리포트를 선택하세요.</p>
              )}
            </div>
          </div>
        )}
      </section>
    </>
  )
}
