import { Fragment, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Markdown } from '../components/Markdown'
import { useConsensusStatus } from '../hooks/useConsensusStatus'
import { formatEventDetail, formatProgress, formatTime } from '../lib/format'
import type { ConsensusTheme, InputReport } from '../types'
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

export function OpsPage() {
  const [params, setParams] = useSearchParams()
  const theme = parseTheme(params.get('theme'))
  const [question, setQuestion] = useState(DEFAULT_QUESTION[theme])
  const [inputs, setInputs] = useState<InputReport[]>([])
  const [selectedCount, setSelectedCount] = useState(0)
  const [inputError, setInputError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [previewMd, setPreviewMd] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  const {
    status,
    history,
    fetchError,
    requestingStart,
    requestingStop,
    startRun,
    stopRun,
  } = useConsensusStatus(theme)

  useEffect(() => {
    setQuestion(DEFAULT_QUESTION[theme])
    setExpandedId(null)
    setPreviewMd(null)
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
          setInputError(null)
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setInputError(e instanceof Error ? e.message : String(e))
        }
      })
    return () => {
      cancelled = true
    }
  }, [theme])

  const busy =
    status.state === 'starting' ||
    status.state === 'active' ||
    status.state === 'stopping'
  const badge = fetchError ? 'offline' : STATE_CLASS[status.state]
  const themeHistory = history.filter((h) => h.theme === theme)

  async function onStart() {
    if (!window.confirm(`${THEME_LABEL[theme]} 컨센서스를 시작할까요?`)) return
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
      setPreviewMd(data.filled_frame || data.consensus_frame || '(프레임 없음)')
    } catch (e) {
      setPreviewMd(e instanceof Error ? e.message : String(e))
    } finally {
      setPreviewLoading(false)
    }
  }

  return (
    <>
      <header className="monitor-header">
        <h1>운영</h1>
        <p className="lede">
          섹터별 입력 확인 · 실행 · 진행 감시 · run 이력입니다.
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
          이 섹터 최신으로 비교
        </Link>
      </section>

      <section className={`panel badge-panel state-${badge}`}>
        <p className="badge-label">런</p>
        <p className="badge-value">
          {fetchError ? 'API Offline' : status.label}
        </p>
        <p className="section-note">
          {status.run
            ? `${THEME_LABEL[status.run.theme as ConsensusTheme] ?? status.run.theme} · ${status.run.asset_id}`
            : '실행 중인 런 없음'}
        </p>
        <p className="section-note">
          progress: {formatProgress(status.progress)}
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
            Stop 요청
          </button>
        )}
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>실행</h2>
        </div>
        <label>
          Question
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
          {requestingStart ? '시작 중…' : 'Start'}
        </button>
        {!status.can_start && (
          <p className="section-note">이미 실행 중인 런이 있습니다.</p>
        )}
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>입력</h2>
          <p className="section-note">
            선정 예정 {selectedCount} / {inputs.length}
          </p>
        </div>
        {inputError && <p className="error-line">{inputError}</p>}
        <table className="data-table">
          <thead>
            <tr>
              <th>선정</th>
              <th>제목</th>
              <th>증권사</th>
              <th>일자</th>
              <th>쪽</th>
              <th>quality</th>
            </tr>
          </thead>
          <tbody>
            {inputs.map((r) => (
              <tr key={r.id}>
                <td>{r.will_select ? '✓' : '—'}</td>
                <td>{r.title}</td>
                <td>{r.provider ?? '—'}</td>
                <td>{r.published_at ?? '—'}</td>
                <td>{r.page_count ?? '—'}</td>
                <td>
                  {r.quality_pass === true
                    ? 'pass'
                    : r.quality_pass === false
                      ? `fail/${r.quality_scope ?? '?'}`
                      : 'pending'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>이벤트</h2>
        </div>
        <ul className="event-list">
          {status.events.length === 0 && (
            <li className="section-note">이벤트 없음</li>
          )}
          {status.events.map((ev) => (
            <li key={ev.id}>
              <span className="mono">{formatTime(ev.at)}</span>{' '}
              <strong>
                {ev.stage}/{ev.event}
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
              <th>asset</th>
              <th>state</th>
              <th>ended</th>
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
                <tr>
                  <td className="mono">{h.asset_id}</td>
                  <td>{h.state}</td>
                  <td>{formatTime(h.ended_at)}</td>
                  <td>
                    <button
                      type="button"
                      className="btn ghost"
                      onClick={() => void togglePreview(h.id)}
                    >
                      {expandedId === h.id ? '접기' : '프레임'}
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
