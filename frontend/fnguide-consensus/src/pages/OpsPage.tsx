import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Markdown } from '../components/Markdown'
import { useConsensusStatus } from '../hooks/useConsensusStatus'
import { formatEventDetail, formatProgress, formatTime } from '../lib/format'
import {
  FRAME_TAB,
  NAV,
  labelRunSlot,
  labelRunState,
  labelStage,
} from '../lib/labels'
import { parseTheme, themePath } from '../lib/theme'
import type { ConsensusTheme } from '../types'
import { DEFAULT_QUESTION, STATE_CLASS, THEME_LABEL } from '../types'

export function OpsPage() {
  const { theme: raw } = useParams()
  const theme = parseTheme(raw)
  const [question, setQuestion] = useState(DEFAULT_QUESTION[theme])
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

  const themeHistory = useMemo(
    () => history.filter((h) => h.theme === theme),
    [history, theme],
  )

  useEffect(() => {
    setQuestion(DEFAULT_QUESTION[theme])
    setExpandedId(null)
    setPreviewMd(null)
  }, [theme])

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
        <h1>
          {THEME_LABEL[theme]} · {NAV.ops}
        </h1>
        <p className="lede">
          컨센서스 생성과 진행·이력을 관리합니다. 선별 심사평·후보 풀은{' '}
          <Link className="text-link" to={themePath(theme, 'select')}>
            {NAV.select}
          </Link>
          에서 봅니다.
        </p>
      </header>

      <section className={`panel badge-panel state-${badge}`}>
        <p className="badge-label">현재 실행</p>
        <p className="badge-value">
          {fetchError ? 'API 연결 끊김' : status.label}
        </p>
        <p className="section-note">
          {status.run
            ? status.run.theme === theme
              ? '이 섹터에서 진행 중'
              : `${THEME_LABEL[status.run.theme as ConsensusTheme] ?? status.run.theme} 섹터에서 진행 중`
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
            생성 시작 시 팩 선별(골격≤10 + 참고) 후 골격·채움까지 한 번에
            실행합니다. 결과는{' '}
            <Link className="text-link" to={themePath(theme, 'select')}>
              {NAV.select}
            </Link>
            에서 확인합니다.
          </p>
        )}
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
              <th>실행</th>
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
            {themeHistory.map((h, i) => (
              <Fragment key={h.id}>
                <tr>
                  <td>{labelRunSlot(i, h.state)}</td>
                  <td>{labelRunState(h.state)}</td>
                  <td>{formatTime(h.ended_at)}</td>
                  <td>
                    <Link
                      className="btn ghost"
                      to={`${themePath(theme, 'select')}?run=${h.id}`}
                    >
                      {NAV.select}
                    </Link>{' '}
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
