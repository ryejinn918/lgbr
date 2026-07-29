import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCollectionJob } from '../../hooks/useCollectionJob'
import { useSessionStatus } from '../../hooks/useSessionStatus'
import { CRAWL_CLASS, formatProgress, formatTime } from '../../lib/format'
import { getMediaSource } from '../../lib/mediaSources'

const PERIOD_OPTIONS = [3, 6, 12] as const
const HUB = getMediaSource('accenture')?.hubUrl ?? ''

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

/** Accenture US: search (Research Report list-while-download) + optional CDP adhoc. */
export function AccentureRunPage() {
  const [periodMonths, setPeriodMonths] = useState(3)
  const [maxPages, setMaxPages] = useState(20)
  const [limit, setLimit] = useState('')
  const session = useSessionStatus()
  const collection = useCollectionJob({
    source: 'accenture',
    capability: 'search',
  })

  const crawl = session.crawl
  const crawlBusy =
    crawl.state === 'starting' ||
    crawl.state === 'active' ||
    crawl.state === 'stopping'
  const job = collection.status
  const searchBusy =
    job.state === 'starting' ||
    job.state === 'active' ||
    job.state === 'stopping'
  const canStartAdhoc = crawl.can_start === true && !crawlBusy && !searchBusy
  const canStartSearch = job.can_start === true && !searchBusy && !crawlBusy
  const badgeState = session.fetchError
    ? 'offline'
    : CRAWL_CLASS[searchBusy ? job.state : crawl.state] ?? 'ended'
  const crawlProgress = crawl.progress ?? crawl.crawl?.progress ?? {}
  const searchProgress = formatSearchProgress(
    (job.progress ?? job.job?.progress ?? undefined) as
      | Record<string, unknown>
      | undefined,
  )
  const isAccentureAdhoc = crawl.crawl?.mode === 'accenture'
  const cdpPort = crawl.crawl?.cdp_port
  const badgeValue = session.fetchError || collection.fetchError
    ? 'API Offline'
    : searchBusy
      ? `Accenture · 검색 · ${job.label}`
      : isAccentureAdhoc
        ? `Accenture · 애드혹 · ${crawl.label}`
        : crawlBusy
          ? 'Accenture · 대기 (다른 세션이 브라우저 사용 중)'
          : job.job
            ? `Accenture · ${job.label}`
            : 'Accenture · 유휴'

  async function onStartAdhoc() {
    if (!window.confirm(`Accenture US 애드혹을 시작할까요?\n${HUB}`)) return
    try {
      await session.startCrawl('accenture')
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '실행 실패')
    }
  }

  async function onStartSearch() {
    const pages = Math.min(50, Math.max(1, Number(maxPages) || 20))
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
    if (
      !window.confirm(
        `Accenture US 검색(Research Report)을 시작할까요?\n최근 ${months}개월 · 최대 ${pages}페이지 · 다운로드 상한 ${limLabel}`,
      )
    ) {
      return
    }
    try {
      await collection.startSearch({
        maxPages: pages,
        periodMonths: months,
        catalog: 'us',
        ...(lim != null ? { limit: lim } : {}),
      })
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '시작 실패')
    }
  }

  async function onStopAdhoc() {
    if (!window.confirm('Accenture 애드혹 브라우저를 종료할까요?')) return
    try {
      await session.requestLogout()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '종료 요청 실패')
    }
  }

  async function onStopSearch() {
    if (!window.confirm('Accenture 검색 작업을 중단할까요?')) return
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
      <p className="account-line">
        US Insights Index에서 Research Report를 최신순으로 돌며 PDF를 받습니다.
        애드혹은 허브 분석용 Chrome+CDP입니다.
      </p>

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

      {isAccentureAdhoc && cdpPort && !session.fetchError ? (
        <p className="account-line">
          CDP <code>http://127.0.0.1:{String(cdpPort)}</code>
          {typeof crawlProgress.url === 'string'
            ? ` · ${crawlProgress.url}`
            : ''}
        </p>
      ) : null}
      {!session.fetchError && crawlBusy ? (
        <p className="account-line">{formatProgress(crawlProgress)}</p>
      ) : null}

      <p className="account-line">
        문서: <Link to="/docs/reports/accenture">Accenture 보고서</Link>
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
        <button
          type="button"
          disabled={!canStartAdhoc || session.requestingStart}
          onClick={() => void onStartAdhoc()}
        >
          {session.requestingStart ? '시작 중…' : '애드혹'}
        </button>
        <button
          type="button"
          disabled={
            (!crawlBusy && !isAccentureAdhoc) || session.requestingStop
          }
          onClick={() => void onStopAdhoc()}
        >
          {session.requestingStop ? '종료 중…' : '애드혹 종료'}
        </button>
      </div>
    </section>
  )
}
