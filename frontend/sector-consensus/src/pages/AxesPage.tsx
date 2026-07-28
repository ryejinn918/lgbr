import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useConsensusStatusContext } from '../hooks/ConsensusStatusContext'
import {
  BLOCKED_BY_OPEN_RUN,
  BLOCKED_BY_THIS_SECTOR,
  NAV,
} from '../lib/labels'
import { isLiveState, openRunForTheme } from '../lib/runState'
import { parseTheme, themePath } from '../lib/theme'
import type { SelectCriteria } from '../types'
import { THEME_LABEL } from '../types'

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

export function AxesPage() {
  const { theme: raw } = useParams()
  const theme = parseTheme(raw)
  const {
    status,
    history,
    requestingStart,
    startRun,
    continueRun,
    refresh,
  } = useConsensusStatusContext()

  const [thesis, setThesis] = useState('')
  const [cutLogic, setCutLogic] = useState('')
  const [pillars, setPillars] = useState('')
  const [continuing, setContinuing] = useState(false)

  const themeHistory = useMemo(
    () => history.filter((h) => h.theme === theme).slice(0, 2),
    [history, theme],
  )

  const openRun = openRunForTheme(status, theme)

  const lastEnded = useMemo(() => {
    if (openRun) return null
    return (
      themeHistory.find((h) => h.state === 'ended' || h.state === 'error') ?? null
    )
  }, [openRun, themeHistory])

  const lastCriteria = asCriteria(lastEnded?.criteria)
  const openCriteria = asCriteria(openRun?.criteria)
  const pillarsKey = JSON.stringify(openCriteria?.pillar_sketch || [])

  const busy = isLiveState(openRun?.state)
  const awaiting = openRun?.state === 'awaiting'

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
  const axesLocked = hasCut
  const cuttingAxes = Boolean(busy && !axesLocked)
  const showWorkForm = Boolean(openRun)
  const showLastAxes = Boolean(
    !openRun &&
      lastCriteria?.thesis &&
      (lastCriteria.pillar_sketch?.length ?? 0) >= 2,
  )

  async function onCut() {
    if (
      !window.confirm(
        `${THEME_LABEL[theme]} 섹터 분석 축 잡기를 시작할까요? 끝나면 여기서 확인·수정합니다.`,
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

  return (
    <>
      <header className="monitor-header">
        <h1>
          {THEME_LABEL[theme]} · {NAV.axes}
        </h1>
        <p className="lede">
          산업 긴장을 분석 축으로 정리한 뒤, 확인한 다음 보고서 선별로 이어갑니다.
        </p>
      </header>

      <section className="panel">
        <button
          type="button"
          className="btn"
          disabled={!status.can_start || busy || requestingStart}
          onClick={() => void onCut()}
        >
          {requestingStart ? '시작 중…' : '분석 축 잡기'}
        </button>
        {!status.can_start ? (
          <p className="section-note">{BLOCKED_BY_OPEN_RUN}</p>
        ) : busy ? (
          <p className="section-note">{BLOCKED_BY_THIS_SECTOR}</p>
        ) : null}
      </section>

      {showWorkForm && (
        <section className="panel">
          <div className="section-head">
            <h2>긴장 · 축</h2>
          </div>
          {cuttingAxes && (
            <p className="section-note">분석 축 잡는 중…</p>
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
            </div>
          )}
        </section>
      )}

      {showLastAxes && lastCriteria && (
        <section className="panel">
          <div className="section-head">
            <h2>최근 축</h2>
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
            <Link className="text-link" to={themePath(theme, 'select')}>
              {NAV.select}
            </Link>
            ·
            <Link className="text-link" to={themePath(theme, 'frames')}>
              {NAV.frames}
            </Link>
          </p>
        </section>
      )}
    </>
  )
}
