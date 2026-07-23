import type { CrawlEvent, CrawlState, SessionState } from '../types'

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
  all: '판정전체',
  pass: '적합',
  fail: '부적합',
  pending: '미감사',
  unauditable: '파일 없음',
}

/** 품질 감사 잡 stats → 현업용 한 줄 */
export function formatAuditStats(
  stats: Record<string, number> | null | undefined,
): string | null {
  if (!stats) return null
  const bits = [
    `대상 ${stats.candidates ?? 0}건`,
    `적합 ${stats.pass ?? 0}`,
    `부적합 ${stats.reject ?? 0}`,
    `추출실패 ${stats.extract_fail ?? 0}`,
    `API오류 ${stats.fail_api ?? 0}`,
  ]
  return bits.join(' · ')
}

export const THEME_LABEL: Record<string, string> = {
  all: '테마전체',
  datacenter: '데이터센터',
  ai: 'AI',
  physical_ai: 'Physical AI',
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const ms = Date.parse(value)
  if (Number.isNaN(ms)) return value
  return new Date(ms).toLocaleString()
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
  const skippedBlind = progress.skipped_blind
  const rpt =
    progress.current_rpt_id != null ? String(progress.current_rpt_id) : null
  const bits: string[] = []
  if (stage) bits.push(`stage=${stage}`)
  if (downloaded != null || limit != null) {
    bits.push(`downloaded=${downloaded ?? 0}/${limit ?? '?'}`)
  }
  if (listed != null) bits.push(`listed=${listed}`)
  if (skippedBlind != null) bits.push(`skipped_blind=${skippedBlind}`)
  if (rpt) bits.push(`rpt=${rpt}`)
  return bits.length ? bits.join(' · ') : JSON.stringify(progress)
}

export const SESSION_EVENT_LABEL: Record<string, string> = {
  login_start: '로그인 시작',
  login_ok: '로그인 완료',
  login_fail: '로그인 실패',
  touch: '세션 유지',
  logout_request: '로그아웃 요청',
  logout_ok: '로그아웃 완료',
  external_logout: '외부 로그아웃',
  error: '세션 오류',
}

export function formatEventDetail(detail: Record<string, unknown>): string {
  const keys = [
    'rpt_id',
    'reason',
    'error',
    'file_name',
    'title',
    'list_page',
    'candidates',
    'blind',
    'existing',
    'total',
    'summary',
    'message',
    'url',
    'step',
  ]
  const parts: string[] = []
  for (const key of keys) {
    if (detail[key] != null && detail[key] !== '') {
      let value = String(detail[key])
      if (key === 'title' && value.length > 48) {
        value = `${value.slice(0, 45)}...`
      }
      parts.push(`${key}=${value}`)
    }
  }
  return parts.join(' · ')
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
