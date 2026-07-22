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
  all: '품질전체',
  pass: '통과',
  fail: '탈락',
  pending: '미감사',
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
