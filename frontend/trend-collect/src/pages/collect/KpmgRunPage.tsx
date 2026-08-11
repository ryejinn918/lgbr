import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCollectionJob } from '../../hooks/useCollectionJob'
import {
  DEFAULT_KPMG_PROFILE,
  KPMG_PROFILES,
  getKpmgProfile,
  type KpmgProfileId,
} from '../../lib/kpmgProfiles'
import { CRAWL_CLASS, formatTime } from '../../lib/format'

const PERIOD_OPTIONS = [3, 6, 12] as const

function formatSearchProgress(progress: Record<string, unknown> | undefined) {
  if (!progress) return null
  const bits: string[] = []
  if (progress.profile != null)
    bits.push(`profile ${String(progress.profile)}`)
  if (progress.query != null) bits.push(`q=${String(progress.query)}`)
  if (progress.pages_done != null)
    bits.push(`목록 ${String(progress.pages_done)}`)
  if (progress.listed != null) bits.push(`목록항목 ${String(progress.listed)}`)
  if (progress.downloaded != null)
    bits.push(`수집 ${String(progress.downloaded)}`)
  if (progress.skipped_no_download != null)
    bits.push(`수집불가 ${String(progress.skipped_no_download)}`)
  if (progress.skipped_existing != null)
    bits.push(`기존 ${String(progress.skipped_existing)}`)
  if (progress.skipped_old != null)
    bits.push(`기간외 ${String(progress.skipped_old)}`)
  if (progress.current_title)
    bits.push(String(progress.current_title).slice(0, 60))
  return bits.length ? bits.join(' · ') : null
}

/** KPMG: hub/theme Cludo search list-while-download. */
export function KpmgRunPage() {
  const [profileId, setProfileId] = useState<KpmgProfileId>(
    DEFAULT_KPMG_PROFILE,
  )
  const [periodMonths, setPeriodMonths] = useState<number>(
    () => getKpmgProfile(DEFAULT_KPMG_PROFILE)?.periodMonths ?? 3,
  )
  const [maxPages, setMaxPages] = useState(20)
  const [limit, setLimit] = useState('')
  const [itemDelaySeconds, setItemDelaySeconds] = useState(2)
  const collection = useCollectionJob({
    source: 'kpmg',
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
  const activeProfile = getKpmgProfile(profileId)
  const badgeValue = collection.fetchError
    ? 'API Offline'
    : searchBusy
      ? `KPMG · 검색 중`
      : job.job
        ? `KPMG · ${job.label}`
        : `KPMG · 유휴`

  function onProfileChange(next: KpmgProfileId) {
    setProfileId(next)
    const prof = getKpmgProfile(next)
    if (prof) setPeriodMonths(prof.periodMonths)
  }

  async function onStartSearch() {
    const pages = Math.min(50, Math.max(1, Number(maxPages) || 20))
    const months = PERIOD_OPTIONS.includes(
      periodMonths as (typeof PERIOD_OPTIONS)[number],
    )
      ? periodMonths
      : (activeProfile?.periodMonths ?? 3)
    const limRaw = String(limit).trim()
    const lim =
      limRaw === ''
        ? undefined
        : Math.min(200, Math.max(1, Number(limRaw) || 0)) || undefined
    const limLabel = lim == null ? '제한 없음' : String(lim)
    const delay = Math.min(10, Math.max(0, Number(itemDelaySeconds) || 0))
    const profileLabel = activeProfile?.label ?? profileId
    if (
      !window.confirm(
        `KPMG 검색을 시작할까요?\n${profileLabel} · 최근 ${months}개월 · 최대 ${pages}페이지 · 처리 상한 ${limLabel} · 간격 ${delay}초`,
      )
    ) {
      return
    }
    try {
      await collection.startSearch({
        maxPages: pages,
        periodMonths: months,
        catalog: 'us',
        profile: profileId,
        itemDelaySeconds: delay,
        ...(lim != null ? { limit: lim } : {}),
      })
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '시작 실패')
    }
  }

  async function onStopSearch() {
    if (!window.confirm('KPMG 검색을 중단할까요?')) return
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
        허브(*)와 프로필별 Cludo 검색어로 인사이트를 수집합니다.
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
        문서: <Link to="/docs/reports/kpmg">KPMG 보고서</Link>
      </p>

      <div className="actions">
        <label className="limit-field">
          프로필
          <select
            value={profileId}
            onChange={(e) =>
              onProfileChange(e.target.value as KpmgProfileId)
            }
            disabled={searchBusy}
          >
            {KPMG_PROFILES.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
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
