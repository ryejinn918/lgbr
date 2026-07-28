import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCollectionJob } from '../../hooks/useCollectionJob'
import { CRAWL_CLASS, formatTime } from '../../lib/format'

const SOURCE = 'arg'

function formatBodyProgress(progress: Record<string, unknown> | undefined) {
  if (!progress) return null
  const bits: string[] = []
  if (progress.done != null && progress.total != null) {
    bits.push(`${String(progress.done)}/${String(progress.total)}`)
  }
  if (progress.fetched != null) bits.push(`성공 ${String(progress.fetched)}`)
  if (progress.failed != null) bits.push(`실패 ${String(progress.failed)}`)
  if (progress.current_key != null)
    bits.push(`idxno ${String(progress.current_key)}`)
  if (progress.message) bits.push(String(progress.message))
  else if (progress.stop_reason) bits.push(String(progress.stop_reason))
  return bits.length ? bits.join(' · ') : null
}

export function ArgFetchBodyRunPage() {
  const [limit, setLimit] = useState(200)
  const [delaySeconds, setDelaySeconds] = useState(1)
  const collection = useCollectionJob({
    source: SOURCE,
    capability: 'fetch_body',
  })
  const job = collection.status
  const busy =
    job.state === 'starting' ||
    job.state === 'active' ||
    job.state === 'stopping'
  const canStart = job.can_start === true && !busy
  const badgeState = collection.fetchError
    ? 'offline'
    : CRAWL_CLASS[job.state] ?? 'ended'
  const progressLine = formatBodyProgress(
    (job.progress ?? job.job?.progress ?? undefined) as
      | Record<string, unknown>
      | undefined,
  )

  async function onStart() {
    const lim = Math.min(1000, Math.max(1, Number(limit) || 200))
    const delay = Math.min(5, Math.max(0.5, Number(delaySeconds) || 1))
    if (
      !window.confirm(
        `ARG 본문 없는 기사 최대 ${lim}건을 채울까요? (요청 간격 ${delay}초)`,
      )
    ) {
      return
    }
    try {
      await collection.startFetchBody({ limit: lim, delaySeconds: delay })
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '시작 실패')
    }
  }

  async function onStop() {
    if (!window.confirm('본문 채우기 작업을 중단할까요?')) return
    try {
      await collection.stopFeed()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '중단 실패')
    }
  }

  return (
    <section className={`panel badge-panel state-${badgeState}`}>
      <p className="badge-label">본문 채우기 · 본문읽기 · 실행</p>
      <p className="badge-value">
        {collection.fetchError
          ? 'API Offline'
          : `ARG · 본문읽기 · ${job.label}`}
      </p>
      {job.job?.started_at && !collection.fetchError ? (
        <p className="account-line">
          시작 {formatTime(job.job.started_at)}
          {job.job.ended_at ? ` · 종료 ${formatTime(job.job.ended_at)}` : ''}
        </p>
      ) : null}
      {progressLine && !collection.fetchError ? (
        <p className="account-line">{progressLine}</p>
      ) : null}
      {job.job?.message && !collection.fetchError ? (
        <p className="account-line">{job.job.message}</p>
      ) : null}
      <p className="account-line">
        리스트:{' '}
        <Link to="/collect/arg/list/feed">피드 실행</Link>
        {' · '}
        결과 문서:{' '}
        <Link to="/docs/articles">기사</Link>
      </p>

      <div className="actions">
        <label className="limit-field">
          최대 건수
          <input
            type="number"
            min={1}
            max={1000}
            value={limit}
            disabled={busy || collection.requestingStart}
            onChange={(e) => setLimit(Number(e.target.value))}
          />
        </label>
        <label className="limit-field">
          간격(초)
          <input
            type="number"
            min={0.5}
            max={5}
            step={0.5}
            value={delaySeconds}
            disabled={busy || collection.requestingStart}
            onChange={(e) => setDelaySeconds(Number(e.target.value))}
          />
        </label>
        <button
          type="button"
          disabled={!canStart || collection.requestingStart}
          onClick={() => void onStart()}
        >
          {collection.requestingStart ? '시작 중…' : '본문 가져오기'}
        </button>
        <button
          type="button"
          disabled={!busy || collection.requestingStop}
          onClick={() => void onStop()}
        >
          {collection.requestingStop ? '중단 요청…' : '중단'}
        </button>
      </div>
    </section>
  )
}
