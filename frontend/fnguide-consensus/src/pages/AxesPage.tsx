import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useConsensusStatus } from '../hooks/useConsensusStatus'
import { NAV, labelRunState, labelStage } from '../lib/labels'
import { parseTheme, themePath } from '../lib/theme'
import type { ConsensusTheme, SelectCriteria } from '../types'
import { STATE_CLASS, THEME_LABEL } from '../types'

function asCriteria(raw: unknown): SelectCriteria | null {
  if (!raw || typeof raw !== 'object') return null
  return raw as SelectCriteria
}

function pillarsText(list: string[] | null | undefined): string {
  return (list || []).join('\n')
}

function parsePillars(text: string): string[] {
  return text
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)
}

function isOpenState(state: string | undefined): boolean {
  return (
    state === 'starting' ||
    state === 'active' ||
    state === 'stopping' ||
    state === 'awaiting'
  )
}

export function AxesPage() {
  const { theme: raw } = useParams()
  const theme = parseTheme(raw)
  const {
    status,
    history,
    fetchError,
    requestingStart,
    requestingStop,
    startRun,
    stopRun,
    continueRun,
    refresh,
  } = useConsensusStatus(theme)

  const [thesis, setThesis] = useState('')
  const [cutLogic, setCutLogic] = useState('')
  const [pillars, setPillars] = useState('')
  const [continuing, setContinuing] = useState(false)

  const themeHistory = useMemo(
    () => history.filter((h) => h.theme === theme).slice(0, 2),
    [history, theme],
  )

  const openRun =
    status.run?.theme === theme && isOpenState(status.run.state)
      ? status.run
      : null

  const lastEnded = useMemo(() => {
    if (openRun) return null
    return (
      themeHistory.find((h) => h.state === 'ended' || h.state === 'error') ?? null
    )
  }, [openRun, themeHistory])

  const lastCriteria = asCriteria(lastEnded?.criteria)
  const openCriteria = asCriteria(openRun?.criteria)
  const pillarsKey = JSON.stringify(openCriteria?.pillar_sketch || [])

  const busy =
    openRun?.state === 'starting' ||
    openRun?.state === 'active' ||
    openRun?.state === 'stopping'
  const awaiting = openRun?.state === 'awaiting'
  const badge = fetchError
    ? 'offline'
    : openRun
      ? STATE_CLASS[openRun.state] || 'idle'
      : 'idle'

  useEffect(() => {
    if (!openRun) {
      setThesis(() => '')
      setCutLogic(() => '')
      setPillars(() => '')
      setContinuing(() => false)
      return
    }
    const c = asCriteria(openRun.criteria)
    setThesis(() => String(c?.thesis || ''))
    setCutLogic(() => String(c?.cut_logic || ''))
    setPillars(() => pillarsText(c?.pillar_sketch))
    setContinuing(() => false)
  }, [
    theme,
    openRun?.id,
    openRun?.state,
    openCriteria?.thesis,
    openCriteria?.cut_logic,
    pillarsKey,
  ])

  const canEdit = Boolean(awaiting && openRun?.id)
  const hasCut = Boolean(thesis.trim() && parsePillars(pillars).length >= 2)
  const stage = String(status.progress?.stage || '')
  const resumeFrom = openCriteria?.resume_from
  const axesLocked = hasCut
  const cuttingAxes = Boolean(busy && !axesLocked)
  const downstreamBusy = Boolean(busy && axesLocked)
  const showWorkForm = Boolean(openRun)
  const showLastAxes = Boolean(
    !openRun &&
      lastCriteria?.thesis &&
      (lastCriteria.pillar_sketch?.length ?? 0) >= 2,
  )

  async function onCut() {
    if (
      !window.confirm(
        `${THEME_LABEL[theme]} 섹터 축 가르기를 시작할까요? 끝나면 여기서 확인·수정합니다.`,
      )
    ) {
      return
    }
    setThesis(() => '')
    setCutLogic(() => '')
    setPillars(() => '')
    setContinuing(() => false)
    try {
      await startRun(theme)
      await refresh()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '시작 실패')
    }
  }

  async function onContinue(untilSelect: boolean) {
    if (!openRun?.id || !hasCut) return
    setContinuing(() => true)
    try {
      await continueRun(openRun.id, {
        thesis: thesis.trim(),
        cut_logic: cutLogic.trim(),
        pillar_sketch: parsePillars(pillars),
        until: untilSelect ? 'select' : undefined,
      })
      await refresh()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : '계속 실패')
    } finally {
      setContinuing(() => false)
    }
  }

  const otherBusyTheme =
    status.run && status.run.theme !== theme && isOpenState(status.run.state)
      ? (status.run.theme as ConsensusTheme)
      : null

  const note = useMemo((): ReactNode => {
    if (cuttingAxes) {
      return '축 가르기 진행 중… 새 긴장이 채워질 때까지 기다립니다.'
    }
    if (downstreamBusy) {
      const isFrames =
        resumeFrom === 'doc' ||
        stage === 'doc' ||
        stage === 'consensus' ||
        stage === 'fill'
      const isSelect = resumeFrom === 'select' || stage === 'select'
      if (isFrames) {
        return (
          <>
            논지 생성 진행 중… 축은 확정된 상태입니다.{' '}
            <Link className="text-link" to={themePath(theme, 'frames')}>
              {NAV.frames}
            </Link>
            에서 확인하세요.
          </>
        )
      }
      if (isSelect) {
        return (
          <>
            보고서 선별 진행 중… 축은 확정된 상태입니다.{' '}
            <Link className="text-link" to={themePath(theme, 'select')}>
              {NAV.select}
            </Link>
            에서 확인하세요.
          </>
        )
      }
      return (
        <>
          후속 단계 진행 중… (축은 확정됨){' '}
          <Link className="text-link" to={themePath(theme, 'select')}>
            {NAV.select}
          </Link>
          ·
          <Link className="text-link" to={themePath(theme, 'frames')}>
            {NAV.frames}
          </Link>
        </>
      )
    }
    if (awaiting) return '축을 확인·수정한 뒤 선별 또는 전체를 이어가세요.'
    if (otherBusyTheme)
      return `${THEME_LABEL[otherBusyTheme]} 섹터에서 작업 중입니다.`
    return '축 가르기를 실행하면 아래에 이번 긴장이 채워집니다.'
  }, [
    cuttingAxes,
    downstreamBusy,
    stage,
    resumeFrom,
    awaiting,
    otherBusyTheme,
    theme,
  ])

  const statusLabel = fetchError
    ? 'API 연결 끊김'
    : downstreamBusy && stage
      ? labelStage(stage)
      : openRun
        ? labelRunState(openRun.state)
        : '대기'

  return (
    <>
      <header className="monitor-header">
        <h1>
          {THEME_LABEL[theme]} · {NAV.axes}
        </h1>
        <p className="lede">
          산업 긴장을 먼저 자르고, 확인한 뒤 보고서 선별로 이어갑니다.
        </p>
      </header>

      <section className={`panel badge-panel state-${badge}`}>
        <p className="badge-label">이번 작업</p>
        <p className="badge-value">{statusLabel}</p>
        <p className="section-note">{note}</p>
        {(busy || awaiting) && (
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
          <h2>축 가르기</h2>
        </div>
        <button
          type="button"
          className="btn"
          disabled={!status.can_start || busy || requestingStart}
          onClick={() => void onCut()}
        >
          {requestingStart ? '시작 중…' : '축 가르기 실행'}
        </button>
        {!status.can_start && (
          <p className="section-note">
            다른 작업이 열려 있습니다.{' '}
            <Link className="text-link" to={themePath(theme, 'ops')}>
              {NAV.ops}
            </Link>
            에서 상태를 확인하세요.
          </p>
        )}
      </section>

      {showWorkForm && (
        <section className="panel">
          <div className="section-head">
            <h2>긴장 · 축</h2>
          </div>
          {cuttingAxes && (
            <p className="section-note">가르는 중… 결과가 나오면 여기에 채워집니다.</p>
          )}
          {downstreamBusy && (
            <p className="section-note">
              축은 확정된 상태입니다. 진행은{' '}
              <Link className="text-link" to={themePath(theme, 'select')}>
                {NAV.select}
              </Link>
              ·
              <Link className="text-link" to={themePath(theme, 'frames')}>
                {NAV.frames}
              </Link>
              탭에서 보세요.
            </p>
          )}
          <label className="section-note" htmlFor="thesis">
            긴장 (한 줄)
          </label>
          <textarea
            id="thesis"
            className="mono"
            rows={2}
            value={thesis}
            readOnly={!canEdit}
            placeholder={cuttingAxes ? '생성 중…' : ''}
            onChange={(e) => {
              const v = e.target.value
              setThesis(() => v)
            }}
            style={{ width: '100%', marginBottom: '0.75rem' }}
          />
          <label className="section-note" htmlFor="cut_logic">
            분리 이유
          </label>
          <textarea
            id="cut_logic"
            className="mono"
            rows={4}
            value={cutLogic}
            readOnly={!canEdit}
            placeholder={cuttingAxes ? '생성 중…' : ''}
            onChange={(e) => {
              const v = e.target.value
              setCutLogic(() => v)
            }}
            style={{ width: '100%', marginBottom: '0.75rem' }}
          />
          <label className="section-note" htmlFor="pillars">
            축 (줄마다 하나, 2–4개)
          </label>
          <textarea
            id="pillars"
            className="mono"
            rows={5}
            value={pillars}
            readOnly={!canEdit}
            placeholder={cuttingAxes ? '생성 중…' : ''}
            onChange={(e) => {
              const v = e.target.value
              setPillars(() => v)
            }}
            style={{ width: '100%', marginBottom: '0.75rem' }}
          />
          {awaiting && (
            <div className="chip-row" style={{ gap: '0.5rem', flexWrap: 'wrap' }}>
              <button
                type="button"
                className="btn"
                disabled={!hasCut || continuing}
                onClick={() => void onContinue(true)}
              >
                {continuing ? '진행 중…' : '이 축으로 선별만'}
              </button>
              <button
                type="button"
                className="btn"
                disabled={!hasCut || continuing}
                onClick={() => void onContinue(false)}
              >
                {continuing ? '진행 중…' : '이 축으로 전체 계속'}
              </button>
              <Link className="btn ghost" to={themePath(theme, 'select')}>
                {NAV.select} 보기
              </Link>
            </div>
          )}
        </section>
      )}

      {!openRun && !showLastAxes && (
        <section className="panel">
          <p className="section-note">
            축 가르기를 실행하면 이번 긴장·축이 여기에 나타납니다.
          </p>
        </section>
      )}

      {showLastAxes && lastCriteria && (
        <section className="panel">
          <div className="section-head">
            <h2>최근 축</h2>
            <p className="section-note">이전 실행 결과 (읽기 전용)</p>
          </div>
          <p className="section-note">긴장</p>
          <p className="select-review-body">{lastCriteria.thesis}</p>
          {lastCriteria.cut_logic ? (
            <>
              <p className="section-note">분리 이유</p>
              <p className="select-review-body">{lastCriteria.cut_logic}</p>
            </>
          ) : null}
          <p className="section-note">축</p>
          <ul className="select-review-list">
            {(lastCriteria.pillar_sketch || []).map((p, i) => (
              <li key={`${i}-${p}`}>{p}</li>
            ))}
          </ul>
          <p className="section-note">
            선별·논지 결과는{' '}
            <Link className="text-link" to={themePath(theme, 'select')}>
              {NAV.select}
            </Link>
            ·
            <Link className="text-link" to={themePath(theme, 'frames')}>
              {NAV.frames}
            </Link>
            에서 확인합니다.
          </p>
        </section>
      )}
    </>
  )
}
