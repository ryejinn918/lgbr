import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Markdown } from '../components/Markdown'
import { useConsensusStatus } from '../hooks/useConsensusStatus'
import { formatTime } from '../lib/format'
import {
  FRAME_TAB,
  NAV,
  labelDocStatus,
  labelRunSlot,
  labelRunState,
} from '../lib/labels'
import { parseTheme, themePath } from '../lib/theme'
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
  slice_count?: number | null
  exclude_reason?: string | null
  select_why?: string | null
}

function isBusyState(state: string | null | undefined): boolean {
  return state === 'starting' || state === 'active' || state === 'stopping'
}

export function FramesPage() {
  const { theme: raw } = useParams()
  const theme = parseTheme(raw)
  const [searchParams] = useSearchParams()
  const runFromUrl = searchParams.get('run')
  const [packRunId, setPackRunId] = useState<string | null>(runFromUrl)
  const [filled, setFilled] = useState<string | null>(null)
  const [consensus, setConsensus] = useState<string | null>(null)
  const [docs, setDocs] = useState<DocRow[]>([])
  const [tab, setTab] = useState<ViewTab>('filled')
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null)
  const [compressMd, setCompressMd] = useState<string | null>(null)
  const [compressLoading, setCompressLoading] = useState(false)
  const [compressError, setCompressError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { status, history } = useConsensusStatus(theme)

  const themeHistory = useMemo(
    () => history.filter((h) => h.theme === theme).slice(0, 2),
    [history, theme],
  )

  // status.run falls back to latest ended run when idle — only force-select when busy.
  const openThemeRun =
    status.run?.theme === theme && isBusyState(status.run.state)
      ? status.run
      : null

  const packRun = useMemo(() => {
    if (openThemeRun) return openThemeRun
    if (packRunId) {
      const hit = themeHistory.find((h) => h.id === packRunId)
      if (hit) return hit
    }
    return themeHistory[0] ?? null
  }, [openThemeRun, packRunId, themeHistory])

  const packIndex = packRun
    ? themeHistory.findIndex((h) => h.id === packRun.id)
    : -1
  const packLabel =
    packRun != null
      ? labelRunSlot(packIndex < 0 ? 0 : packIndex, packRun.state)
      : null

  useEffect(() => {
    setPackRunId(runFromUrl)
    setFilled(null)
    setConsensus(null)
    setDocs([])
    setSelectedDocId(null)
    setCompressMd(null)
    setCompressError(null)
    setError(null)
    setTab('filled')
  }, [theme, runFromUrl])

  useEffect(() => {
    const runId = packRun?.id
    if (!runId) {
      setFilled(null)
      setConsensus(null)
      setDocs([])
      setSelectedDocId(null)
      setError(null)
      return
    }
    let cancelled = false
    const load = () => {
      void Promise.all([
        fetch(`/api/consensus/runs/${runId}/outputs`).then(async (r) => {
          const d = await r.json()
          if (!r.ok || !d.ok) throw new Error(d.message || `HTTP ${r.status}`)
          return d
        }),
        fetch(`/api/consensus/runs/${runId}/docs`).then(async (r) => {
          const d = await r.json()
          if (!r.ok || !d.ok) throw new Error(d.message || `docs HTTP ${r.status}`)
          return d
        }),
      ])
        .then(([outData, docData]) => {
          if (cancelled) return
          setFilled(outData.filled_frame ?? null)
          setConsensus(outData.consensus_frame ?? null)
          const items = (docData.items ?? []) as DocRow[]
          setDocs(items)
          setSelectedDocId((prev) => {
            if (prev && items.some((x) => x.report_id === prev)) return prev
            const first = items.find((x) => x.has_compress) ?? items[0] ?? null
            return first?.report_id ?? null
          })
          setError(null)
        })
        .catch((e) => {
          if (!cancelled) {
            setFilled(null)
            setConsensus(null)
            setDocs([])
            setError(e instanceof Error ? e.message : String(e))
          }
        })
    }
    load()
    const busy = isBusyState(packRun.state)
    const t = busy ? window.setInterval(load, 3_000) : 0
    return () => {
      cancelled = true
      if (t) window.clearInterval(t)
    }
  }, [packRun?.id, packRun?.state])

  const selectedDocs = useMemo(
    () =>
      docs.filter((d) => d.role === 'selected' || d.role === 'fill_extra'),
    [docs],
  )
  const coreDocs = useMemo(
    () => selectedDocs.filter((d) => d.role === 'selected'),
    [selectedDocs],
  )
  const biblioDocs = useMemo(
    () => selectedDocs.filter((d) => d.role === 'fill_extra'),
    [selectedDocs],
  )
  const materialGroups = useMemo(
    () =>
      [
        { key: 'core' as const, label: '골격용', items: coreDocs },
        { key: 'biblio' as const, label: '참고용', items: biblioDocs },
      ].filter((g) => g.items.length > 0),
    [coreDocs, biblioDocs],
  )
  const selectedDoc =
    selectedDocs.find((d) => d.report_id === selectedDocId) ??
    selectedDocs[0] ??
    null

  useEffect(() => {
    if (!packRun?.id || !selectedDoc) {
      setCompressMd(null)
      setCompressError(null)
      setCompressLoading(false)
      return
    }
    if (!selectedDoc.has_compress) {
      setCompressMd(null)
      setCompressError(null)
      setCompressLoading(false)
      return
    }
    let cancelled = false
    setCompressLoading(true)
    setCompressError(null)
    setCompressMd(null)
    void fetch(
      `/api/consensus/runs/${packRun.id}/docs/${selectedDoc.report_id}/compress`,
    )
      .then(async (r) => {
        const d = await r.json()
        if (!r.ok || !d.ok) throw new Error(d.message || `HTTP ${r.status}`)
        if (!cancelled) {
          setCompressMd(d.compress_md ?? null)
          setCompressLoading(false)
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setCompressMd(null)
          setCompressError(e instanceof Error ? e.message : String(e))
          setCompressLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [packRun?.id, selectedDoc?.report_id, selectedDoc?.has_compress])

  const frameBody = tab === 'filled' ? filled : tab === 'consensus' ? consensus : null
  const runTimeNote = packRun
    ? isBusyState(packRun.state)
      ? labelRunState(packRun.state)
      : formatTime(packRun.ended_at)
    : null

  return (
    <>
      <header className="monitor-header">
        <h1>
          {THEME_LABEL[theme]} · {NAV.frames}
        </h1>
        <p className="lede">
          요약·골격·살 붙인 논지와, 근거로 쓴 보고서 요약을 봅니다.
        </p>
        {packRun && packLabel ? (
          <p className="section-note">
            {packLabel} · {runTimeNote} · {packRun.question}
          </p>
        ) : (
          <p className="section-note">
            이 섹터에 실행 이력이 없습니다.{' '}
            <Link className="text-link" to={themePath(theme, 'axes')}>
              {NAV.axes}에서 시작
            </Link>
          </p>
        )}
        {error && <p className="error-line">{error}</p>}
      </header>

      <section className="panel">
        {themeHistory.length > 1 && (
          <div className="chip-row">
            {themeHistory.map((h, i) => (
              <button
                key={h.id}
                type="button"
                className={`chip ${packRun?.id === h.id ? 'active' : ''}`}
                onClick={() => setPackRunId(h.id)}
              >
                {labelRunSlot(i, h.state)}
              </button>
            ))}
          </div>
        )}
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
            골격에 근거와 수치를 채워 넣은 본문입니다. 채팅 답변의 기본
            참고입니다.
          </p>
        )}
        {tab === 'consensus' && (
          <p className="section-note">
            여러 보고서가 모인 총론·핵심 주제 수준의 골격입니다.
          </p>
        )}
        {tab === 'materials' && (
          <p className="section-note">
            골격용·참고용으로 나눈 선별 보고서와 문서별 요약입니다.
            {selectedDocs.length > 0
              ? ` · 골격용 ${coreDocs.length} · 참고용 ${biblioDocs.length}`
              : ''}
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
                <li className="section-note">선별된 보고서 없음</li>
              )}
              {materialGroups.map((g) => (
                <li key={g.key} className="materials-group">
                  <p className={`materials-group-label role-${g.key}`}>
                    {g.label} · {g.items.length}건
                  </p>
                  <ul className="materials-group-items">
                    {g.items.map((d) => {
                      const role = d.role === 'fill_extra' ? 'biblio' : 'core'
                      return (
                        <li key={d.report_id}>
                          <button
                            type="button"
                            className={`materials-item role-${role}${
                              selectedDoc?.report_id === d.report_id
                                ? ' active'
                                : ''
                            }`}
                            onClick={() => setSelectedDocId(d.report_id)}
                          >
                            <span className="materials-item-head">
                              <span className={`role-badge role-${role}`}>
                                {role === 'core' ? '골격' : '참고'}
                              </span>
                              <span className="materials-title">{d.title}</span>
                            </span>
                            <span className="section-note">
                              {d.provider ?? '—'} ·{' '}
                              {labelDocStatus(d.doc_status)}
                              {d.has_compress ? '' : ' · 요약 없음'}
                            </span>
                            {d.select_why ? (
                              <span className="section-note materials-why">
                                {d.select_why}
                              </span>
                            ) : null}
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                </li>
              ))}
            </ul>
            <div className="materials-body">
              {selectedDoc ? (
                <>
                  <p className="materials-item-head">
                    <span
                      className={`role-badge role-${
                        selectedDoc.role === 'fill_extra' ? 'biblio' : 'core'
                      }`}
                    >
                      {selectedDoc.role === 'fill_extra' ? '참고' : '골격'}
                    </span>
                    <a
                      className="text-link materials-title"
                      href={`/api/reports/${selectedDoc.report_id}/file`}
                      download
                      title="보고서 받기"
                    >
                      {selectedDoc.title}
                    </a>
                  </p>
                  <p className="section-note">
                    {selectedDoc.provider ?? '—'}
                    {selectedDoc.slice_count != null
                      ? ` · 요약 구간 ${selectedDoc.slice_count}개`
                      : ''}
                  </p>
                  {selectedDoc.select_why ? (
                    <p className="select-review-body">{selectedDoc.select_why}</p>
                  ) : null}
                  {compressLoading ? (
                    <p className="section-note">요약 불러오는 중…</p>
                  ) : compressError ? (
                    <p className="error-line">{compressError}</p>
                  ) : selectedDoc.has_compress && compressMd ? (
                    <div className="frame-scroll tall">
                      <Markdown>{compressMd}</Markdown>
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
