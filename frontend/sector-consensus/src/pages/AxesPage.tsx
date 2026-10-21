import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { SelectPanels } from '../components/SelectPanels'
import { useConsensusStatusContext } from '../hooks/ConsensusStatusContext'
import {
  clearAxisDraft,
  readAxisDraft,
  sameAxisFields,
  writeAxisDraft,
  type AxisFields,
} from '../lib/axisDraft'
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

function AxesReview({
  thesis,
  cutLogic,
  pillars,
}: {
  thesis: string
  cutLogic?: string | null
  pillars: string[]
}) {
  return (
    <>
      <p className="section-note">주제</p>
      <p className="select-review-body">{thesis}</p>
      {cutLogic ? (
        <>
          <p className="section-note">축 나눈 이유</p>
          <p className="select-review-body">{cutLogic}</p>
        </>
      ) : null}
      <p className="section-note">분석 축</p>
      <ul className="select-review-list">
        {pillars.map((p, i) => (
          <li key={`${i}-${p}`}>{p}</li>
        ))}
      </ul>
    </>
  )
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
  const [draftSaved, setDraftSaved] = useState(false)
  const [draftConflict, setDraftConflict] = useState(false)
  const draftBaseRef = useRef<AxisFields | null>(null)

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
  const openRunId = openRun?.id
  const openRunState = openRun?.state
  const serverAxes = useMemo<AxisFields>(
    () => ({
      thesis: String(openCriteria?.thesis || ''),
      cutLogic: String(openCriteria?.cut_logic || ''),
      pillars: pillarsText(openCriteria?.pillar_sketch),
    }),
    [
      openCriteria?.thesis,
      openCriteria?.cut_logic,
      openCriteria?.pillar_sketch,
    ],
  )

  const busy = isLiveState(openRun?.state)
  const awaiting = openRun?.state === 'awaiting'

  useEffect(() => {
    if (!openRunId) {
      setThesis(() => '')
      setCutLogic(() => '')
      setPillars(() => '')
      setContinuing(() => false)
      setDraftSaved(() => false)
      setDraftConflict(() => false)
      draftBaseRef.current = null
      return
    }
    const stored =
      openRunState === 'awaiting' ? readAxisDraft(openRunId) : null
    const axes = stored?.values ?? serverAxes
    draftBaseRef.current = stored?.base ?? serverAxes
    setThesis(() => axes.thesis)
    setCutLogic(() => axes.cutLogic)
    setPillars(() => axes.pillars)
    setContinuing(() => false)
    setDraftSaved(() => stored !== null)
    setDraftConflict(() =>
      stored ? !sameAxisFields(stored.base, serverAxes) : false,
    )
  }, [
    theme,
    openRunId,
    openRunState,
    serverAxes,
  ])

  function persistDraft(values: AxisFields) {
    if (!openRun?.id || !awaiting) return
    const base = draftBaseRef.current ?? serverAxes
    writeAxisDraft(openRun.id, base, values, serverAxes)
    setDraftSaved(() => !sameAxisFields(serverAxes, values))
  }

  function resetDraft() {
    if (!openRun?.id) return
    clearAxisDraft(openRun.id)
    draftBaseRef.current = serverAxes
    setThesis(() => serverAxes.thesis)
    setCutLogic(() => serverAxes.cutLogic)
    setPillars(() => serverAxes.pillars)
    setDraftSaved(() => false)
    setDraftConflict(() => false)
  }

  const canEdit = Boolean(awaiting && openRun?.id)
  const hasCut = Boolean(thesis.trim() && parsePillars(pillars).length >= 2)
  const serverHasCut = Boolean(
    serverAxes.thesis.trim() && parsePillars(serverAxes.pillars).length >= 2,
  )
  // Live worker, thesis not yet on server → cutting in progress.
  const cuttingAxes = Boolean(busy && !serverHasCut)
  // Live after continue (or thesis already locked on server while not awaiting).
  const runningLocked = Boolean(openRun && busy && serverHasCut)
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
      clearAxisDraft(openRun.id)
      setDraftSaved(() => false)
      setDraftConflict(() => false)
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
          산업 주제를 분석 축으로 정리한 뒤, 확인하면 보고서 선별까지 이
          화면에서 이어집니다.
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
            <h2>주제 · 분석 축</h2>
          </div>
          {cuttingAxes ? (
            <p className="section-note">분석 축 잡는 중…</p>
          ) : runningLocked ? (
            <>
              <p className="section-note">분석 진행 중 · 축은 잠겨 있습니다.</p>
              <AxesReview
                thesis={serverAxes.thesis}
                cutLogic={serverAxes.cutLogic}
                pillars={parsePillars(serverAxes.pillars)}
              />
            </>
          ) : canEdit ? (
            <>
              <label className="section-note" htmlFor="thesis">
                주제 (한 줄)
              </label>
              <textarea
                id="thesis"
                className="mono"
                rows={2}
                value={thesis}
                onChange={(e) => {
                  const v = e.target.value
                  setThesis(() => v)
                  persistDraft({ thesis: v, cutLogic, pillars })
                }}
                style={{ width: '100%', marginBottom: '0.75rem' }}
              />
              <label className="section-note" htmlFor="cut_logic">
                축 나눈 이유
              </label>
              <textarea
                id="cut_logic"
                className="mono"
                rows={4}
                value={cutLogic}
                onChange={(e) => {
                  const v = e.target.value
                  setCutLogic(() => v)
                  persistDraft({ thesis, cutLogic: v, pillars })
                }}
                style={{ width: '100%', marginBottom: '0.75rem' }}
              />
              <label className="section-note" htmlFor="pillars">
                분석 축 (줄마다 하나, 2–4개)
              </label>
              <textarea
                id="pillars"
                className="mono"
                rows={5}
                value={pillars}
                onChange={(e) => {
                  const v = e.target.value
                  setPillars(() => v)
                  persistDraft({ thesis, cutLogic, pillars: v })
                }}
                style={{ width: '100%', marginBottom: '0.75rem' }}
              />
              {draftSaved && (
                <div className="section-note" role="status">
                  <span>
                    {draftConflict
                      ? '서버의 분석 축이 바뀌었지만 이 브라우저의 편집 초안을 유지하고 있습니다.'
                      : '편집 초안이 이 브라우저에 저장되었습니다.'}
                  </span>{' '}
                  <button
                    type="button"
                    className="text-link"
                    onClick={resetDraft}
                  >
                    서버 축으로 되돌리기
                  </button>
                </div>
              )}
              <div
                className="chip-row"
                style={{ gap: '0.5rem', flexWrap: 'wrap' }}
              >
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
            </>
          ) : serverHasCut ? (
            <AxesReview
              thesis={serverAxes.thesis}
              cutLogic={serverAxes.cutLogic}
              pillars={parsePillars(serverAxes.pillars)}
            />
          ) : (
            <p className="section-note">분석 축을 기다리는 중…</p>
          )}
        </section>
      )}

      {showLastAxes && lastCriteria && (
        <section className="panel">
          <div className="section-head">
            <h2>최근 분석 축</h2>
          </div>
          <AxesReview
            thesis={String(lastCriteria.thesis || '')}
            cutLogic={lastCriteria.cut_logic}
            pillars={lastCriteria.pillar_sketch || []}
          />
          <p className="section-note">
            <Link className="text-link" to={themePath(theme, 'frames')}>
              {NAV.frames}
            </Link>
          </p>
        </section>
      )}
      <SelectPanels />
    </>
  )
}
