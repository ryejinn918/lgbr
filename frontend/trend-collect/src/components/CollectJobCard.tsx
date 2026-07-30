import type { ReactNode } from 'react'
import {
  freshnessClass,
  pickFreshnessAt,
  type FreshnessKind,
} from '../lib/jobFreshness'
import { formatRelative, formatTime } from '../lib/format'

export type CollectJobCardProps = {
  title: string
  /** e.g. 계정 · 리포트 · 검색 */
  meta: string[]
  statusLabel: string
  /** offline | active | ended | error | stale | starting | stopping */
  stateClass: string
  freshnessKind: FreshnessKind
  lastCollectedAt: string | null
  lastDocAt?: string | null
  accountLine?: string | null
  progressLine?: string | null
  links: ReactNode
  stop?: {
    label: string
    disabled: boolean
    onClick: () => void
  } | null
}

const IDLE_STATES = new Set(['ended'])

export function CollectJobCard({
  title,
  meta,
  statusLabel,
  stateClass,
  freshnessKind,
  lastCollectedAt,
  lastDocAt = null,
  accountLine = null,
  progressLine = null,
  links,
  stop = null,
}: CollectJobCardProps) {
  const freshnessAt = pickFreshnessAt(lastCollectedAt, lastDocAt)
  const showFresh = IDLE_STATES.has(stateClass)
  const freshCls = showFresh ? freshnessClass(freshnessAt, freshnessKind) : ''
  const collectedAbs = lastCollectedAt ? formatTime(lastCollectedAt) : null
  const docAbs = lastDocAt ? formatTime(lastDocAt) : null

  return (
    <article className={`job-card state-${stateClass} ${freshCls}`.trim()}>
      <p className="badge-label">{title}</p>
      {meta.length > 0 ? (
        <p className="job-meta">{meta.filter(Boolean).join(' · ')}</p>
      ) : null}
      <p className="badge-value">{statusLabel}</p>
      <p className="account-line" title={collectedAbs ?? undefined}>
        마지막 수집{' '}
        {lastCollectedAt ? formatRelative(lastCollectedAt) : '—'}
      </p>
      {lastDocAt != null || freshnessKind === 'report' ? (
        <p className="account-line" title={docAbs ?? undefined}>
          최근 문서 {lastDocAt ? formatRelative(lastDocAt) : '—'}
        </p>
      ) : null}
      {accountLine ? <p className="account-line">{accountLine}</p> : null}
      {progressLine ? <p className="account-line">{progressLine}</p> : null}
      <p className="account-line">{links}</p>
      {stop ? (
        <div className="actions">
          <button
            type="button"
            disabled={stop.disabled}
            onClick={stop.onClick}
          >
            {stop.label}
          </button>
        </div>
      ) : null}
    </article>
  )
}
