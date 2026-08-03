import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCollectionJob } from '../../hooks/useCollectionJob'
import { CRAWL_CLASS, formatTime } from '../../lib/format'
import {
  DEFAULT_PWC_CATALOG,
  PWC_CATALOGS,
  getPwcCatalog,
  type PwcCatalogId,
} from '../../lib/pwcCatalogs'

const PERIOD_OPTIONS = [3, 6, 12] as const

function formatSearchProgress(progress: Record<string, unknown> | undefined) {
  if (!progress) return null
  const bits: string[] = []
  if (progress.catalog_label != null || progress.catalog != null)
    bits.push(String(progress.catalog_label || progress.catalog))
  if (progress.pages_done != null)
    bits.push(`목록 ${String(progress.pages_done)}`)
  if (progress.listed != null) bits.push(`목록항목 ${String(progress.listed)}`)
  if (progress.downloaded != null)
    bits.push(`수집 ${String(progress.downloaded)}`)
  if (progress.skipped_no_download != null)
    bits.push(`수집불가 ${String(progress.skipped_no_download)}`)
  if (progress.skipped_existing != null)
    bits.push(`기존 ${String(progress.skipped_existing)}`)
  if (progress.current_title)
    bits.push(String(progress.current_title).slice(0, 60))
  return bits.length ? bits.join(' · ') : null
}

/** PwC list/search: automated list-while-download. */
export function PwcAdhocRunPage() {
  const [catalog, setCatalog] = useState<PwcCatalogId>(DEFAULT_PWC_CATALOG)
  const [periodMonths, setPeriodMonths] = useState(3)
  const [maxPages, setMaxPages] = useState(20)
  const [itemDelaySeconds, setItemDelaySeconds] = useState(2)
  /** Empty = no download cap (full period). */
  const [limit, setLimit] = useState('')
  const collection = useCollectionJob({ source: 'pwc', capability: 'search' })
  const catalogMeta = getPwcCatalog(catalog)

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
      ? 'PwC · 검색 중'
      : job.job
        ? `PwC · ${job.label}`
        : 'PwC · 유휴'

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
    const delay = Math.min(10, Math.max(0, Number(itemDelaySeconds) || 0))
    if (
      !window.confirm(
        `PwC 검색을 시작할까요?\n${catalogMeta.label} · 최근 ${months}개월 · 최대 ${pages}페이지 · 처리 상한 ${limLabel} · 간격 ${delay}초`,
      )
    ) {
      return
    }
    try {
      await collection.startSearch({
        maxPages: pages,
        periodMonths: months,
        catalog,
        itemDelaySeconds: delay,
        ...(lim != null ? { limit: lim } : {}),
      })
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '시작 실패')
    }
  }

  async function onStopSearch() {
    if (!window.confirm('PwC 검색을 중단할까요?')) return
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
        목록을 수집해 요약을 만듭니다.
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

      <p className="account-line">
        목록 타입:{' '}
        <Link to="/collect/pwc/list/search/types">한국 / 국제</Link>
        {' · '}
        문서: <Link to="/docs/reports/pwc">PwC 보고서</Link>
      </p>

      <div className="actions">
        <label className="limit-field">
          목록
          <select
            value={catalog}
            onChange={(e) => setCatalog(e.target.value as PwcCatalogId)}
            disabled={searchBusy}
          >
            {PWC_CATALOGS.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
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
          처리 상한
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
