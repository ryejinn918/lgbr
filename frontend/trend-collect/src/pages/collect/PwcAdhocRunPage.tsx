import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCollectionJob } from '../../hooks/useCollectionJob'
import { useSessionStatus } from '../../hooks/useSessionStatus'
import { CRAWL_CLASS, formatProgress, formatTime } from '../../lib/format'
import { crawlModeTypeLabel } from '../../lib/collectNav'

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
  if (progress.current_title)
    bits.push(String(progress.current_title).slice(0, 60))
  return bits.length ? bits.join(' · ') : null
}

/** PwC list/search: adhoc CDP browser + automated list-while-download. */
export function PwcAdhocRunPage() {
  const [periodMonths, setPeriodMonths] = useState(3)
  const [maxPages, setMaxPages] = useState(20)
  /** Empty = no download cap (full period). */
  const [limit, setLimit] = useState('')
  const session = useSessionStatus()
  const collection = useCollectionJob({ source: 'pwc', capability: 'search' })

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
  const isPwcAdhoc = crawl.crawl?.mode === 'pwc'
  const cdpPort = crawl.crawl?.cdp_port

  async function onStartAdhoc() {
    if (
      !window.confirm(
        'PwC 애드혹 크롤을 시작할까요? (로그인 없이 Chrome+CDP)',
      )
    ) {
      return
    }
    try {
      await session.startCrawl('pwc')
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
        `PwC 검색(list-while-download)을 시작할까요?\n최근 ${months}개월 · 최대 ${pages}페이지 · 다운로드 상한 ${limLabel}`,
      )
    ) {
      return
    }
    try {
      await collection.startSearch({
        maxPages: pages,
        periodMonths: months,
        ...(lim != null ? { limit: lim } : {}),
      })
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '시작 실패')
    }
  }

  async function onStopAdhoc() {
    if (!window.confirm('PwC 애드혹 브라우저를 종료할까요?')) return
    try {
      await session.requestLogout()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '종료 요청 실패')
    }
  }

  async function onStopSearch() {
    if (!window.confirm('PwC 검색 작업을 중단할까요?')) return
    try {
      await collection.stopFeed()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '중단 실패')
    }
  }

  return (
    <section className={`panel badge-panel state-${badgeState}`}>
      <p className="badge-label">리스트 발굴 · 검색 · 실행</p>
      <p className="badge-value">
        {session.fetchError || collection.fetchError
          ? 'API Offline'
          : searchBusy
            ? `PwC · 검색 · ${job.label}`
            : `PwC · ${crawlModeTypeLabel(crawl.crawl?.mode)} · ${crawl.label}`}
      </p>
      <p className="account-line">
        검색 실행이 목록을 넘기며 PDF를 바로 받습니다 (리스트 전용 잡 없음).
        애드혹은 페이지 소스 분석용 Chrome+CDP입니다.
      </p>

      <div className="form-row">
        <label>
          기간(개월)
          <select
            value={periodMonths}
            onChange={(e) => setPeriodMonths(Number(e.target.value))}
            disabled={searchBusy}
          >
            {PERIOD_OPTIONS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label>
          max pages
          <input
            type="number"
            min={1}
            max={50}
            value={maxPages}
            disabled={searchBusy}
            onChange={(e) => setMaxPages(Number(e.target.value))}
          />
        </label>
        <label>
          download limit
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
      </div>

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

      {isPwcAdhoc && cdpPort && !session.fetchError ? (
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
        문서: <Link to="/docs/reports/pwc">PwC 보고서</Link>
        {' · '}
        본문 탭: <Link to="/collect/pwc/body/download">다운로드 상태</Link>
      </p>

      <div className="button-row">
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
          disabled={(!crawlBusy && !isPwcAdhoc) || session.requestingStop}
          onClick={() => void onStopAdhoc()}
        >
          {session.requestingStop ? '종료 중…' : '애드혹 종료'}
        </button>
      </div>
    </section>
  )
}
