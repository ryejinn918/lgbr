import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Markdown } from '../components/Markdown'
import { useConsensusStatus } from '../hooks/useConsensusStatus'
import { formatEventDetail, formatProgress, formatTime } from '../lib/format'
import { FRAME_TAB, NAV, labelRunState, labelStage } from '../lib/labels'
import type {
  ConsensusTheme,
  InputReport,
  RunDoc,
  SelectCriteria,
} from '../types'
import {
  DEFAULT_QUESTION,
  STATE_CLASS,
  THEME_LABEL,
} from '../types'

const THEMES: ConsensusTheme[] = ['datacenter', 'ai', 'physical_ai']

function parseTheme(raw: string | null): ConsensusTheme {
  if (raw && THEMES.includes(raw as ConsensusTheme)) return raw as ConsensusTheme
  return 'datacenter'
}

function asCriteria(raw: unknown): SelectCriteria | null {
  if (!raw || typeof raw !== 'object') return null
  return raw as SelectCriteria
}

export function OpsPage() {
  const [params, setParams] = useSearchParams()
  const theme = parseTheme(params.get('theme'))
  const [question, setQuestion] = useState(DEFAULT_QUESTION[theme])
  const [inputs, setInputs] = useState<InputReport[]>([])
  const [selectedCount, setSelectedCount] = useState(0)
  const [secondaryCount, setSecondaryCount] = useState(0)
  const [poolQpCount, setPoolQpCount] = useState<number | null>(null)
  const [inputError, setInputError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [previewMd, setPreviewMd] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [packRunId, setPackRunId] = useState<string | null>(null)
  const [runDocs, setRunDocs] = useState<RunDoc[]>([])
  const [docsError, setDocsError] = useState<string | null>(null)

  const {
    status,
    history,
    fetchError,
    requestingStart,
    requestingStop,
    startRun,
    stopRun,
  } = useConsensusStatus(theme)

  const themeHistory = useMemo(
    () => history.filter((h) => h.theme === theme),
    [history, theme],
  )

  const openThemeRun =
    status.run?.theme === theme ? status.run : null

  const packRun = useMemo(() => {
    if (openThemeRun) return openThemeRun
    if (packRunId) {
      const hit = themeHistory.find((h) => h.id === packRunId)
      if (hit) return hit
    }
    return themeHistory[0] ?? null
  }, [openThemeRun, packRunId, themeHistory])

  const packCriteria = asCriteria(packRun?.criteria)
  const coreDocs = runDocs.filter((d) => d.role === 'selected')
  const biblioDocs = runDocs.filter((d) => d.role === 'fill_extra')
  const packDocs = [...coreDocs, ...biblioDocs]
  const hasPackReview =
    !!packCriteria?.coverage_notes ||
    (!!packCriteria?.pillar_sketch && packCriteria.pillar_sketch.length > 0)

  useEffect(() => {
    setQuestion(DEFAULT_QUESTION[theme])
    setExpandedId(null)
    setPreviewMd(null)
    setPoolQpCount(null)
    setPackRunId(null)
    setRunDocs([])
    setDocsError(null)
  }, [theme])

  useEffect(() => {
    let cancelled = false
    void fetch(`/api/consensus/inputs?theme=${theme}`)
      .then(async (r) => {
        const d = await r.json()
        if (!r.ok || !d.ok) throw new Error(d.message || `HTTP ${r.status}`)
        if (!cancelled) {
          setInputs(d.items ?? [])
          setSelectedCount(d.selected_count ?? 0)
          setSecondaryCount(d.secondary_count ?? 0)
          const qp = d.criteria?.quality_pass_count
          setPoolQpCount(typeof qp === 'number' ? qp : null)
          setInputError(null)
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setInputError(e instanceof Error ? e.message : String(e))
          setPoolQpCount(null)
        }
      })
    return () => {
      cancelled = true
    }
  }, [theme])

  useEffect(() => {
    const runId = packRun?.id
    if (!runId) {
      setRunDocs([])
      setDocsError(null)
      return
    }
    let cancelled = false
    const load = () => {
      void fetch(`/api/consensus/runs/${runId}/docs`)
        .then(async (r) => {
          const d = await r.json()
          if (!r.ok || !d.ok) throw new Error(d.message || `HTTP ${r.status}`)
          if (!cancelled) {
            setRunDocs((d.items ?? []) as RunDoc[])
            setDocsError(null)
          }
        })
        .catch((e) => {
          if (!cancelled) {
            setDocsError(e instanceof Error ? e.message : String(e))
          }
        })
    }
    load()
    const busy =
      packRun.state === 'starting' ||
      packRun.state === 'active' ||
      packRun.state === 'stopping'
    const t = busy ? window.setInterval(load, 3_000) : 0
    return () => {
      cancelled = true
      if (t) window.clearInterval(t)
    }
  }, [packRun?.id, packRun?.state])

  const busy =
    status.state === 'starting' ||
    status.state === 'active' ||
    status.state === 'stopping'
  const badge = fetchError ? 'offline' : STATE_CLASS[status.state]

  async function onStart() {
    if (
      !window.confirm(
        `${THEME_LABEL[theme]} 섹터 컨센서스 생성을 시작할까요?`,
      )
    ) {
      return
    }
    try {
      await startRun(theme, question)
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '시작 실패')
    }
  }

  async function togglePreview(runId: string) {
    if (expandedId === runId) {
      setExpandedId(null)
      setPreviewMd(null)
      return
    }
    setExpandedId(runId)
    setPreviewLoading(true)
    setPreviewMd(null)
    try {
      const res = await fetch(`/api/consensus/runs/${runId}/outputs`)
      const data = await res.json()
      if (!res.ok || !data.ok) throw new Error(data.message || `HTTP ${res.status}`)
      setPreviewMd(
        data.filled_frame || data.consensus_frame || '(논지 없음)',
      )
    } catch (e) {
      setPreviewMd(e instanceof Error ? e.message : String(e))
    } finally {
      setPreviewLoading(false)
    }
  }

  return (
    <>
      <header className="monitor-header">
        <h1>{NAV.ops}</h1>
        <p className="lede">
          섹터별 입력 리포트 확인, 컨센서스 생성, 진행 상황·이력을 관리합니다.
        </p>
      </header>

      <section className="panel">
        <div className="chip-row">
          {THEMES.map((t) => (
            <button
              key={t}
              type="button"
              className={`chip ${theme === t ? 'active' : ''}`}
              onClick={() => setParams({ theme: t }, { replace: true })}
            >
              {THEME_LABEL[t]}
            </button>
          ))}
        </div>
        <Link className="text-link" to={`/?theme=${theme}`}>
          이 섹터 최신으로 {NAV.compare}
        </Link>
      </section>

      <section className={`panel badge-panel state-${badge}`}>
        <p className="badge-label">현재 실행</p>
        <p className="badge-value">
          {fetchError ? 'API 연결 끊김' : status.label}
        </p>
        <p className="section-note">
          {status.run
            ? `${THEME_LABEL[status.run.theme as ConsensusTheme] ?? status.run.theme} · ${status.run.asset_id}`
            : '실행 중인 작업 없음'}
        </p>
        <p className="section-note">
          진행: {formatProgress(status.progress)}
        </p>
        {status.message && <p className="section-note">{status.message}</p>}
        {busy && (
          <button
            type="button"
            className="btn ghost"
            disabled={requestingStop}
            onClick={() => {
              if (!window.confirm('종료를 요청할까요?')) return
              void stopRun().catch((e) =>
                window.alert(e instanceof Error ? e.message : '실패'),
              )
            }}
          >
            종료 요청
          </button>
        )}
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>생성</h2>
        </div>
        <label>
          분석 질문
          <textarea
            rows={2}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="btn"
          disabled={!status.can_start || busy || requestingStart}
          onClick={() => void onStart()}
        >
          {requestingStart ? '시작 중…' : '생성 시작'}
        </button>
        {!status.can_start && (
          <p className="section-note">이미 실행 중인 작업이 있습니다.</p>
        )}
        {theme === 'ai' && (
          <p className="section-note">
            생성 시작 시 팩 선정(골격≤10 + 참고) 후 골격·채움까지 한 번에 실행합니다.
            선정 이유·심사평은 아래 「실행 선정」에 이 런 기준으로 표시됩니다.
          </p>
        )}
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>실행 선정</h2>
          <p className="section-note">
            {packRun
              ? `${packRun.asset_id} · ${labelRunState(packRun.state)} · 골격 ${coreDocs.length} · 참고 ${biblioDocs.length}`
              : '이 섹터 실행 이력이 없습니다. 생성 시작하면 여기에 선정 결과가 남습니다.'}
          </p>
        </div>
        {docsError && <p className="error-line">{docsError}</p>}
        {hasPackReview && (
          <div className="select-review">
            <h3>선정 심사평</h3>
            {packCriteria?.coverage_notes ? (
              <p className="select-review-body">
                {packCriteria.coverage_notes}
              </p>
            ) : null}
            {packCriteria?.pillar_sketch &&
            packCriteria.pillar_sketch.length > 0 ? (
              <>
                <p className="section-note">축 초안</p>
                <ul className="select-review-list">
                  {packCriteria.pillar_sketch.map((p, i) => (
                    <li key={`${i}-${p}`}>{p}</li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>
        )}
        {packRun && packDocs.length === 0 && !docsError && (
          <p className="section-note">
            아직 선정 단계 전입니다. 선정이 끝나면 골격/참고와 사유가 채워집니다.
          </p>
        )}
        {packDocs.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>역할</th>
                <th>제목</th>
                <th>증권사</th>
                <th>쪽</th>
                <th>사유</th>
              </tr>
            </thead>
            <tbody>
              {packDocs.map((d, i) => {
                const role = d.role === 'fill_extra' ? 'biblio' : 'core'
                const prev = i > 0 ? packDocs[i - 1] : null
                const prevRole =
                  prev?.role === 'fill_extra'
                    ? 'biblio'
                    : prev
                      ? 'core'
                      : null
                const showGroup = role !== prevRole
                return (
                  <Fragment key={d.report_id}>
                    {showGroup && (
                      <tr className={`input-group-row role-${role}`}>
                        <td colSpan={5}>
                          {role === 'core'
                            ? `골격논지 (frame) · ${coreDocs.length}건`
                            : `참고문헌 (fill) · ${biblioDocs.length}건`}
                        </td>
                      </tr>
                    )}
                    <tr className={`input-row role-${role}`}>
                      <td>
                        <span className={`role-badge role-${role}`}>
                          {role === 'core' ? '골격' : '참고'}
                        </span>
                      </td>
                      <td>{d.title}</td>
                      <td>{d.provider ?? '—'}</td>
                      <td>{d.page_count ?? '—'}</td>
                      <td title={d.select_why ?? undefined}>
                        {d.select_why ?? '—'}
                      </td>
                    </tr>
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>{theme === 'ai' ? '후보 풀' : '입력 리포트'}</h2>
          <p className="section-note">
            {theme === 'ai' ? (
              <>
                후보 {inputs.length}
                {poolQpCount != null ? ` · 품질통과 ${poolQpCount}` : ''}
                {' · '}선정은 생성 시작 시 (위 「실행 선정」)
              </>
            ) : (
              <>
                선정 {selectedCount}
                {secondaryCount > 0 ? ` · 참고 ${secondaryCount}` : ''} /{' '}
                {inputs.length}
              </>
            )}
          </p>
        </div>
        {inputError && <p className="error-line">{inputError}</p>}
        <table className="data-table">
          <thead>
            <tr>
              {theme !== 'ai' && <th>역할</th>}
              <th>제목</th>
              <th>출처</th>
              <th>증권사</th>
              <th>일자</th>
              <th>쪽</th>
              <th>품질</th>
              {theme !== 'ai' && <th>사유</th>}
            </tr>
          </thead>
          <tbody>
            {inputs.map((r) => {
              if (theme === 'ai') {
                return (
                  <tr
                    key={r.id}
                    className={
                      r.quality_pass === true
                        ? 'input-row'
                        : 'input-row role-omit'
                    }
                  >
                    <td>{r.title}</td>
                    <td>{r.theme_tag ?? '—'}</td>
                    <td>{r.provider ?? '—'}</td>
                    <td>{r.published_at ?? '—'}</td>
                    <td>{r.page_count ?? '—'}</td>
                    <td>
                      {r.quality_pass === true
                        ? '통과'
                        : r.quality_pass === false
                          ? `미달/${r.quality_scope ?? '?'}`
                          : '대기'}
                    </td>
                  </tr>
                )
              }
              const role = r.will_select
                ? 'core'
                : r.will_fill_extra
                  ? 'biblio'
                  : 'omit'
              return (
                <tr key={r.id} className={`input-row role-${role}`}>
                  <td>
                    <span className={`role-badge role-${role}`}>
                      {role === 'core'
                        ? '골격'
                        : role === 'biblio'
                          ? '참고'
                          : '제외'}
                    </span>
                  </td>
                  <td>{r.title}</td>
                  <td>{r.theme_tag ?? '—'}</td>
                  <td>{r.provider ?? '—'}</td>
                  <td>{r.published_at ?? '—'}</td>
                  <td>{r.page_count ?? '—'}</td>
                  <td>
                    {r.quality_pass === true
                      ? '통과'
                      : r.quality_pass === false
                        ? `미달/${r.quality_scope ?? '?'}`
                        : '대기'}
                  </td>
                  <td title={r.select_why ?? r.exclude_reason ?? undefined}>
                    {role !== 'omit'
                      ? (r.select_why ?? '—')
                      : (r.exclude_reason ?? '—')}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>진행 로그</h2>
        </div>
        <ul className="event-list">
          {status.events.length === 0 && (
            <li className="section-note">로그 없음</li>
          )}
          {status.events.map((ev) => (
            <li key={ev.id}>
              <span className="mono">{formatTime(ev.at)}</span>{' '}
              <strong>
                {labelStage(ev.stage)}/{ev.event}
              </strong>{' '}
              <span className="section-note">
                {formatEventDetail(ev.detail)}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>이력</h2>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>실행 ID</th>
              <th>상태</th>
              <th>종료</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {themeHistory.length === 0 && (
              <tr>
                <td colSpan={4} className="section-note">
                  이력 없음
                </td>
              </tr>
            )}
            {themeHistory.map((h) => (
              <Fragment key={h.id}>
                <tr className={packRun?.id === h.id ? 'input-row role-core' : undefined}>
                  <td className="mono">{h.asset_id}</td>
                  <td>{labelRunState(h.state)}</td>
                  <td>{formatTime(h.ended_at)}</td>
                  <td>
                    <button
                      type="button"
                      className="btn ghost"
                      onClick={() => setPackRunId(h.id)}
                    >
                      선정
                    </button>{' '}
                    <button
                      type="button"
                      className="btn ghost"
                      onClick={() => void togglePreview(h.id)}
                    >
                      {expandedId === h.id ? '접기' : FRAME_TAB.filled}
                    </button>
                  </td>
                </tr>
                {expandedId === h.id && (
                  <tr>
                    <td colSpan={4}>
                      {previewLoading ? (
                        <p className="section-note">불러오는 중…</p>
                      ) : previewMd ? (
                        <div className="frame-scroll compact">
                          <Markdown>{previewMd}</Markdown>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </section>
    </>
  )
}
