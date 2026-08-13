import { Link } from 'react-router-dom'
import {
  freshnessClass,
  pickFreshnessAt,
  type FreshnessKind,
} from '../lib/jobFreshness'
import { formatRelative } from '../lib/format'

export type CollectJobRowProps = {
  title: string
  jobLabel: string
  statusLabel: string
  stateClass: string
  freshnessKind: FreshnessKind
  lastCollectedAt: string | null
  lastDocAt?: string | null
  progressLine?: string | null
  settingsPath: string
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  canStart: boolean
  canStop: boolean
  requesting?: boolean
  queueHint?: string | null
  onStart: () => void
  onStop: () => void
}

const IDLE_STATES = new Set(['ended'])

export function CollectJobRow({
  title,
  jobLabel,
  statusLabel,
  stateClass,
  freshnessKind,
  lastCollectedAt,
  lastDocAt = null,
  progressLine = null,
  settingsPath,
  checked,
  onCheckedChange,
  canStart,
  canStop,
  requesting = false,
  queueHint = null,
  onStart,
  onStop,
}: CollectJobRowProps) {
  const freshnessAt = pickFreshnessAt(lastCollectedAt, lastDocAt)
  const showFresh = IDLE_STATES.has(stateClass)
  const freshCls = showFresh ? freshnessClass(freshnessAt, freshnessKind) : ''

  return (
    <div
      className={`collect-job-row state-${stateClass} ${freshCls}`.trim()}
    >
      <label className="collect-job-check">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onCheckedChange(e.target.checked)}
        />
        <span className="sr-only">
          {title} {jobLabel} 선택
        </span>
      </label>
      <div className="collect-job-main">
        <div className="collect-job-title-line">
          <span className="collect-job-title">{title}</span>
          <span className="collect-job-kind">{jobLabel}</span>
          <span className="collect-job-status">{statusLabel}</span>
        </div>
        <div className="collect-job-meta">
          <span>마지막 수집 {lastCollectedAt ? formatRelative(lastCollectedAt) : '—'}</span>
          {progressLine ? <span>{progressLine}</span> : null}
          {queueHint ? <span className="collect-job-queue">{queueHint}</span> : null}
        </div>
      </div>
      <div className="collect-job-actions">
        {canStop ? (
          <button
            type="button"
            className="logout-btn"
            disabled={requesting}
            onClick={onStop}
          >
            {requesting ? '요청 중…' : '중단'}
          </button>
        ) : (
          <button
            type="button"
            className="run-btn"
            disabled={!canStart || requesting}
            onClick={onStart}
          >
            {requesting ? '시작 중…' : '시작'}
          </button>
        )}
        <Link to={settingsPath}>설정</Link>
      </div>
    </div>
  )
}
