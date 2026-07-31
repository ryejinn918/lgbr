import type {
  CrawlEvent,
  CrawlState,
  QualityExtractMeta,
  SessionState,
} from '../types'

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
  downloaded: '다운됨',
  no_download: '다운불가',
  failed: '실패',
}

export const QUALITY_LABEL: Record<string, string> = {
  all: '검사전체',
  pass: '적합',
  fail: '부적합',
  pending: '미검사',
  unauditable: '파일 없음',
}

/** Non-FnGuide media/consulting: summary extract, not sell-side pass/fail. */
export const QUALITY_LABEL_SUMMARY: Record<string, string> = {
  all: '요약전체',
  pass: '요약됨',
  fail: '추출실패',
  pending: '미요약',
  unauditable: '파일 없음',
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

export function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const ms = Date.parse(value)
  if (Number.isNaN(ms)) return value
  return new Date(ms).toLocaleString()
}

/** Matches crawler quality_audit.PDF_PAGES. */
export const EXTRACT_PDF_PAGES = 5

/** 「요약 입력」: 절단 시 ``첫 5페이지 이후 후략``, 아니면 ``전체``. */
export function formatExtractInput(
  pageCount: number | null | undefined,
  extract?: QualityExtractMeta | null,
): string {
  const total = Number(pageCount)
  const truncatedPages =
    Number.isFinite(total) && total > EXTRACT_PDF_PAGES
  const truncatedFlag =
    extract?.truncated === 1 || extract?.truncated === true
  if (truncatedPages) return `첫 ${EXTRACT_PDF_PAGES}페이지 이후 후략`
  if (truncatedFlag) return '앞부분만 사용'
  if (Number.isFinite(total) && total > 0) return '전체'
  return '—'
}

/** Report published_at (DATE / ISO date) → YYYY-MM-DD. */
export function formatPublishedAt(value: string | null | undefined): string {
  if (!value) return '—'
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(value)
  if (m) return m[1]
  const ms = Date.parse(value)
  if (Number.isNaN(ms)) return value
  const d = new Date(ms)
  const y = d.getFullYear()
  const mo = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${mo}-${day}`
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
  const rpt =
    progress.current_rpt_id != null ? String(progress.current_rpt_id) : null
  const bits: string[] = []
  if (stage) bits.push(`stage=${stage}`)
  if (periodMonths != null) bits.push(`period=${periodMonths}m`)
  if (downloaded != null) {
    bits.push(
      limit != null
        ? `downloaded=${downloaded}/${limit}`
        : `downloaded=${downloaded}`,
    )
  }
  if (listed != null) bits.push(`listed=${listed}`)
  if (skippedBlind != null) bits.push(`skipped_blind=${skippedBlind}`)
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
    if (downloaded != null) bits.push(`downloaded=${downloaded}`)
    if (listed != null) bits.push(`listed=${listed}`)
    if (blind != null) bits.push(`blind=${blind}`)
    if (existing != null) bits.push(`existing=${existing}`)
    if (noDl != null) bits.push(`no_dl=${noDl}`)
    if (failed != null) bits.push(`failed=${failed}`)
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
