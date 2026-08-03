import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCollectionJob } from '../../hooks/useCollectionJob'
import { CRAWL_CLASS, formatTime } from '../../lib/format'

const PERIOD_OPTIONS = [3, 6, 12] as const

function formatSearchProgress(progress: Record<string, unknown> | undefined) {
  if (!progress) return null
  const bits: string[] = []
  if (progress.pages_done != null)
    bits.push(`pages ${String(progress.pages_done)}`)
  if (progress.listed != null) bits.push(`listed ${String(progress.listed)}`)
  if (progress.downloaded != null)
    bits.push(`downloaded ${String(progress.downloaded)}`)
  if (progress.skipped_no_download != null)
    bits.push(`no_pdf ${String(progress.skipped_no_download)}`)
  if (progress.skipped_existing != null)
    bits.push(`existing ${String(progress.skipped_existing)}`)
  if (progress.skipped_old != null)
    bits.push(`old ${String(progress.skipped_old)}`)
  if (progress.current_title)
    bits.push(String(progress.current_title).slice(0, 60))
  return bits.length ? bits.join(' · ') : null
}

/** HBR: search list-while-download. */
export function HbrRunPage() {
  const [periodMonths, setPeriodMonths] = useState(3)
  const [maxPages, setMaxPages] = useState(10)
  const [limit, setLimit] = useState('')
  const [itemDelaySeconds, setItemDelaySeconds] = useState(5)
  const collection = useCollectionJob({
    source: 'hbr',
    capability: 'search',
  })

  const job = collection.status
  const searchBusy =
    job.state === 'starting' ||
    job.state === 'active' ||
    job.state === 'stopping'
  const canStartSearch = job.can_start === true && !searchBusy
  const badgeState = collection.fetchError
    ? 'offline'
    : CRAWL_CLASS[job.state] ?? 'ended'
  const searchProgress = formatSearchProgress(
    (job.progress ?? job.job?.progress ?? undefined) as
      | Record<string, unknown>
      | undefined,
  )
  const badgeValue = collection.fetchError
    ? 'API Offline'
    : searchBusy
      ? `HBR · 검색 중`
      : job.job
        ? `HBR · ${job.label}`
        : `HBR · 유휴`

  async function onStartSearch() {
    const pages = Math.min(50, Math.max(1, Number(maxPages) || 10))
    const months = PERIOD_OPTIONS.includes(
      periodMonths as (typeof PERIOD_OPTIONS)[number],
    )
      ? periodMonths
      : 3
    const limRaw = String(limit).trim()
    const lim =
      limRaw === ''
        ? undefined
        : Math.min(200, Math.max(1, Number(limRaw) || 0)) || undefined
    const limLabel = lim == null ? '제한 없음' : String(lim)
    const delay = Math.min(10, Math.max(0, Number(itemDelaySeconds) || 0))
    if (
      !window.confirm(
        `HBR 검색을 시작할까요?\n최근 ${months}개월 · 최대 ${pages}페이지 · 다운로드 상한 ${limLabel} · 간격 ${delay}초`,
      )
    ) {
      return
    }
    try {
      await collection.startSearch({
        maxPages: pages,
        periodMonths: months,
        catalog: 'us',
        itemDelaySeconds: delay,
        ...(lim != null ? { limit: lim } : {}),
      })
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '시작 실패')
    }
  }

  async function onStopSearch() {
    if (!window.confirm('HBR 검색을 중단할까요?')) return
    try {
      await collection.stopFeed()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '중단 실패')
    }
  }

  return (
    <section className={`panel badge-panel state-${badgeState}`}>
      <p className="badge-label">검색 · 실행</p>
      <p className="badge-value">{badgeValue}</p>
      <p className="account-line">로그인한 뒤 최신 목록에서 본문을 받습니다.</p>

      {job.job?.started_at && !collection.fetchError ? (
        <p className="account-line">
          검색 시작 {formatTime(job.job.started_at)}
          {job.job.ended_at ? ` · 종료 ${formatTime(job.job.ended_at)}` : ''}
          {job.job.message ? ` · ${job.job.message}` : ''}
        </p>
      ) : null}
      {searchProgress ? (
        <p className="account-line">{searchProgress}</p>
      ) : null}

      <p className="account-line">
        문서: <Link to="/docs/reports/hbr">HBR 보고서</Link>
      </p>

      <div className="actions">
        <label className="limit-field">
          기간
          <select
            value={periodMonths}
            onChange={(e) => setPeriodMonths(Number(e.target.value))}
            disabled={searchBusy}
          >
            {PERIOD_OPTIONS.map((m) => (
              <option key={m} value={m}>
                최근 {m}개월
              </option>
            ))}
          </select>
        </label>
        <label className="limit-field">
          최대 페이지
          <input
            type="number"
            min={1}
            max={50}
            value={maxPages}
            disabled={searchBusy}
            onChange={(e) => setMaxPages(Number(e.target.value))}
          />
        </label>
        <label className="limit-field">
          다운로드 상한
          <input
            type="number"
            min={1}
            max={200}
            placeholder="없음"
            value={limit}
            disabled={searchBusy}
            onChange={(e) => setLimit(e.target.value)}
          />
        </label>
        <label className="limit-field">
          간격(초)
          <input
            type="number"
            min={0}
            max={10}
            step={0.5}
            value={itemDelaySeconds}
            disabled={searchBusy}
            onChange={(e) => setItemDelaySeconds(Number(e.target.value))}
          />
        </label>
        <button
          type="button"
          disabled={!canStartSearch || collection.requestingStart}
          onClick={() => void onStartSearch()}
        >
          {collection.requestingStart ? '시작 중…' : '검색 실행'}
        </button>
        <button
          type="button"
          disabled={!searchBusy || collection.requestingStop}
          onClick={() => void onStopSearch()}
        >
          {collection.requestingStop ? '중단 중…' : '검색 중단'}
        </button>
      </div>
    </section>
  )
}
