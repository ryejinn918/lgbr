import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCollectionJob } from '../../hooks/useCollectionJob'
import { CRAWL_CLASS, formatTime } from '../../lib/format'

const SOURCE = 'arg'

function formatFeedProgress(progress: Record<string, unknown> | undefined) {
  if (!progress) return null
  const bits: string[] = []
  if (progress.page != null) bits.push(`page ${String(progress.page)}`)
  if (progress.inserted != null) bits.push(`신규 ${String(progress.inserted)}`)
  if (progress.updated != null) bits.push(`갱신 ${String(progress.updated)}`)
  if (progress.message) bits.push(String(progress.message))
  else if (progress.stop_reason) bits.push(String(progress.stop_reason))
  return bits.length ? bits.join(' · ') : null
}

export function ArgFeedRunPage() {
  const [maxPages, setMaxPages] = useState(50)
  const collection = useCollectionJob({ source: SOURCE })
  const job = collection.status
  const busy =
    job.state === 'starting' ||
    job.state === 'active' ||
    job.state === 'stopping'
  const canStart = job.can_start === true && !busy
  const badgeState = collection.fetchError
    ? 'offline'
    : CRAWL_CLASS[job.state] ?? 'ended'
  const progressLine = formatFeedProgress(
    (job.progress ?? job.job?.progress ?? undefined) as
      | Record<string, unknown>
      | undefined,
  )

  async function onStart() {
    const pages = Math.min(200, Math.max(1, Number(maxPages) || 50))
    if (
      !window.confirm(
        `ARG 리스트 발굴 타입「전체」로 리스트를 가져올까요? (최대 ${pages}페이지, 본문 없음)`,
      )
    ) {
      return
    }
    try {
      await collection.startFeed(pages)
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '시작 실패')
    }
  }

  async function onStop() {
    if (!window.confirm('리스트 발굴 작업을 중단할까요?')) return
    try {
      await collection.stopFeed()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '중단 실패')
    }
  }

  return (
    <section className={`panel badge-panel state-${badgeState}`}>
      <p className="badge-label">리스트 발굴 · 피드 · 실행</p>
      <p className="badge-value">
        {collection.fetchError
          ? 'API Offline'
          : `ARG · 타입 전체 · ${job.label}`}
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
        리스트 발굴 타입:{' '}
        <Link to="/collect/arg/list/feed/types">전체</Link>
        {' · '}
        결과 문서:{' '}
        <Link to="/docs/articles">기사</Link>
      </p>

      <div className="actions">
        <label className="limit-field">
          최대 페이지
          <input
            type="number"
            min={1}
            max={200}
            value={maxPages}
            disabled={busy || collection.requestingStart}
            onChange={(e) => setMaxPages(Number(e.target.value))}
          />
        </label>
        <button
          type="button"
          disabled={!canStart || collection.requestingStart}
          onClick={() => void onStart()}
        >
          {collection.requestingStart ? '시작 중…' : '리스트 가져오기'}
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
