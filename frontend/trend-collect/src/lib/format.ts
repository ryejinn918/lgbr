import type {
  CrawlEvent,
  CrawlState,
  QualityExtractMeta,
  SessionState,
} from '../types'
import { PROFILE_MODE_LABEL, isSearchProfileMode } from './themes'

export const CRAWL_CLASS: Record<CrawlState, string> = {
  starting: 'starting',
  active: 'active',
  stopping: 'stopping',
  ended: 'ended',
  error: 'error',
}

export const SESSION_CLASS: Record<SessionState, string> = {
  logging_in: 'logging_in',
  logged_in: 'logged_in',
  logging_out: 'logging_out',
  ended: 'ended',
  error: 'error',
}

export const STATUS_LABEL: Record<string, string> = {
  all: '전체',
  listed: '목록',
  blind: '본문제한',
  downloaded: '수집됨',
  no_download: '수집불가',
  failed: '실패',
}

export const QUALITY_LABEL: Record<string, string> = {
  all: '검사전체',
  pass: '적합',
  fail: '부적합',
  pending: '미검사',
  unauditable: '요약 불가',
}

/** Non-FnGuide media/consulting: summary extract, not sell-side pass/fail. */
export const QUALITY_LABEL_SUMMARY: Record<string, string> = {
  all: '요약전체',
  pass: '요약됨',
  fail: '추출실패',
  pending: '미요약',
  unauditable: '요약 불가',
}

/** Unified reports tab: sell-side filter vocabulary, pending = 미완료. */
export const QUALITY_LABEL_ALL: Record<string, string> = {
  ...QUALITY_LABEL,
  pending: '미완료',
}

export function qualityLabelsForSource(
  source: string | null | undefined,
): Record<string, string> {
  if (source === 'fnguide') return QUALITY_LABEL
  if (source === 'all') return QUALITY_LABEL_ALL
  return QUALITY_LABEL_SUMMARY
}

/** Per-row label: FnGuide page/row = sell-side; else summary. */
export function qualityLabelForReport(
  quality: string | null | undefined,
  reportSource: string | null | undefined,
  pageSource?: string | null,
): string {
  const key = quality || 'pending'
  const sellSide =
    pageSource === 'fnguide' ||
    ((pageSource === 'all' || !pageSource) && reportSource === 'fnguide')
  const labels = sellSide ? QUALITY_LABEL : QUALITY_LABEL_SUMMARY
  return labels[key] || key
}

export type AuditStatsMode = 'sell_side' | 'summary' | 'all'

/** 품질검사·요약 잡 stats → 현업용 한 줄 */
export function formatAuditStats(
  stats: Record<string, number> | null | undefined,
  mode: AuditStatsMode = 'all',
): string | null {
  if (!stats) return null
  if (mode === 'summary') {
    return [
      `대상 ${stats.candidates ?? 0}건`,
      `요약됨 ${stats.pass ?? 0}`,
      `추출실패 ${stats.extract_fail ?? 0}`,
      `API오류 ${stats.fail_api ?? 0}`,
    ].join(' · ')
  }
  return [
    `대상 ${stats.candidates ?? 0}건`,
    `적합 ${stats.pass ?? 0}`,
    `부적합 ${stats.reject ?? 0}`,
    `추출실패 ${stats.extract_fail ?? 0}`,
    `API오류 ${stats.fail_api ?? 0}`,
  ].join(' · ')
}

export { THEME_LABEL } from './themes'

const KST = 'Asia/Seoul'
const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/

function formatKstYmd(ms: number): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: KST,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(ms))
  const y = parts.find((p) => p.type === 'year')?.value
  const m = parts.find((p) => p.type === 'month')?.value
  const d = parts.find((p) => p.type === 'day')?.value
  if (!y || !m || !d) return '—'
  return `${y}-${m}-${d}`
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const ms = Date.parse(value)
  if (Number.isNaN(ms)) return value
  return new Date(ms).toLocaleString('ko-KR', { timeZone: KST })
}

/** Matches crawler quality_audit.PDF_PAGES. */
export const EXTRACT_PDF_PAGES = 5

/** 「요약 범위」: 절단 시 ``일부``, 아니면 ``전부``. */
export function formatExtractInput(
  pageCount: number | null | undefined,
  extract?: QualityExtractMeta | null,
): string {
  const total = Number(pageCount)
  const truncatedPages =
    Number.isFinite(total) && total > EXTRACT_PDF_PAGES
  const truncatedFlag =
    extract?.truncated === 1 || extract?.truncated === true
  if (truncatedPages) return '일부'
  if (truncatedFlag) return '일부'
  if (Number.isFinite(total) && total > 0) return '전부'
  return '—'
}

/** published_at → YYYY-MM-DD in KST. Date-only (reports DATE) passed through. */
export function formatPublishedAt(value: string | null | undefined): string {
  if (!value) return '—'
  const trimmed = value.trim()
  if (DATE_ONLY_RE.test(trimmed)) return trimmed
  const ms = Date.parse(trimmed)
  if (Number.isNaN(ms)) return value
  return formatKstYmd(ms)
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return '—'
  const ms = Date.parse(value)
  if (Number.isNaN(ms)) return value
  const diff = Date.now() - ms
  if (diff < 60_000) return '방금'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}분 전`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}시간 전`
  return formatTime(value)
}

export function formatProgress(
  progress: Record<string, unknown> | undefined,
): string {
  if (!progress || Object.keys(progress).length === 0) return '—'
  const stage = progress.stage != null ? String(progress.stage) : null
  const downloaded = progress.downloaded
  const listed = progress.listed
  const limit = progress.limit
  const periodMonths = progress.period_months
  const skippedBlind = progress.skipped_blind
  const profileIndex = progress.profile_index
  const profileTotal = progress.profile_total
  const profileMode =
    progress.mode != null && progress.mode !== 'all_profiles'
      ? String(progress.mode)
      : null
  const rpt =
    progress.current_rpt_id != null ? String(progress.current_rpt_id) : null
  const bits: string[] = []
  if (profileIndex != null && profileTotal != null) {
    const modeLabel =
      profileMode && isSearchProfileMode(profileMode)
        ? PROFILE_MODE_LABEL[profileMode]
        : profileMode
    const label = modeLabel
      ? `${profileIndex}/${profileTotal} · ${modeLabel}`
      : `${profileIndex}/${profileTotal}`
    bits.push(label)
  }
  if (stage) bits.push(`stage=${stage}`)
  if (periodMonths != null) bits.push(`period=${periodMonths}m`)
  if (downloaded != null) {
    bits.push(
      limit != null
        ? `수집 ${downloaded}/${limit}`
        : `수집 ${downloaded}`,
    )
  }
  if (listed != null) bits.push(`목록 ${listed}`)
  if (skippedBlind != null) bits.push(`본문제한 ${skippedBlind}`)
  if (rpt) bits.push(`rpt=${rpt}`)
  return bits.length ? bits.join(' · ') : JSON.stringify(progress)
}

/** Prefer progress counters; fall back to a short crawl.message. */
export function formatCrawlResult(
  progress: Record<string, unknown> | undefined,
  message: string | null | undefined,
): string | null {
  if (progress) {
    const downloaded = progress.downloaded
    const listed = progress.listed
    const failed = progress.failed
    const blind = progress.skipped_blind ?? progress.blind
    const existing = progress.skipped_existing
    const noDl = progress.skipped_no_download
    const bits: string[] = []
    if (downloaded != null) bits.push(`수집 ${downloaded}`)
    if (listed != null) bits.push(`목록 ${listed}`)
    if (blind != null) bits.push(`본문제한 ${blind}`)
    if (existing != null) bits.push(`기존 ${existing}`)
    if (noDl != null) bits.push(`수집불가 ${noDl}`)
    if (failed != null) bits.push(`실패 ${failed}`)
    if (bits.length) return bits.join(' ')
  }
  if (!message) return null
  if (message.length > 160) return `${message.slice(0, 157)}...`
  return message
}

export function latestReportTitle(
  events: CrawlEvent[] | undefined,
  rptId: string | null | undefined,
): string | null {
  if (!rptId || !events) return null
  for (const ev of events) {
    const detail = ev.detail || {}
    if (String(detail.rpt_id ?? '') === rptId && detail.title) {
      return String(detail.title)
    }
  }
  return null
}
