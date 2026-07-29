import { Link, useLocation, useParams } from 'react-router-dom'
import { useConsensusStatusContext } from '../hooks/ConsensusStatusContext'
import { formatProgress } from '../lib/format'
import { NAV, labelThemeSector } from '../lib/labels'
import { isLiveState, isOpenState, openRunGlobal, stateClass } from '../lib/runState'
import { parseTab, parseTheme, themePath } from '../lib/theme'

export function AppStatus() {
  const {
    status,
    connectionState,
    hasSnapshot,
    requestingStop,
    stopRun,
  } =
    useConsensusStatusContext()
  const { theme: raw } = useParams()
  const viewTheme = parseTheme(raw)
  const tab = parseTab(useLocation().pathname)

  const run = openRunGlobal(status)

  if (connectionState === 'loading' && !hasSnapshot) {
    return (
      <div className="app-status state-idle" role="status">
        <p className="app-status-text">작업 상태 확인 중…</p>
      </div>
    )
  }

  if (connectionState === 'loading') {
    return (
      <div className="app-status state-idle" role="status">
        <p className="app-status-text">
          API 상태 확인 중 · 마지막 저장 상태: {status.label}
        </p>
      </div>
    )
  }

  if (connectionState === 'offline') {
    const staleProgress = formatProgress(status.progress)
    const staleRun = run
      ? `${labelThemeSector(run.theme)} · ${status.label}${
          staleProgress !== '—' ? ` · ${staleProgress}` : ''
        }`
      : null
    return (
      <div className="app-status state-offline" role="status">
        <p className="app-status-text">
          API 연결 끊김
          {staleRun
            ? ` · 마지막 상태: ${staleRun}`
            : ' · 저장된 작업 상태 없음'}
        </p>
      </div>
    )
  }

  if (!run || !isOpenState(run.state)) return null

  const sector = labelThemeSector(run.theme)
  const live = isLiveState(run.state)
  const progress = formatProgress(status.progress)
  const progressPart =
    live && progress !== '—' ? ` · ${progress}` : ''

  const stopBtn = (
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
      {requestingStop ? '요청 중…' : '종료'}
    </button>
  )

  if (run.state === 'awaiting') {
    const onTarget = tab === 'axes' && viewTheme === run.theme
    return (
      <div className={`app-status state-${stateClass(run.state)}`} role="status">
        <p className="app-status-text">{sector} · 분석 축 확인 필요</p>
        <div className="app-status-actions">
          {!onTarget && (
            <Link className="btn" to={themePath(run.theme, 'axes')}>
              {NAV.axes}
            </Link>
          )}
          {stopBtn}
        </div>
      </div>
    )
  }

  const head =
    run.state === 'stopping'
      ? `${sector} 종료 요청됨 · 다른 실행 불가`
      : `${sector} 진행 중 · 다른 실행 불가`

  return (
    <div className={`app-status state-${stateClass(run.state)}`} role="status">
      <p className="app-status-text">
        {head}
        {progressPart}
      </p>
      <div className="app-status-actions">{stopBtn}</div>
    </div>
  )
}
