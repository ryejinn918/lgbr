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

export function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const ms = Date.parse(value)
  if (Number.isNaN(ms)) return value
  return new Date(ms).toLocaleString()
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
    'path',
    'title',
    'list_page',
    'candidates',
    'blind',
    'total',
  ]
  const parts: string[] = []
  for (const key of keys) {
    if (detail[key] != null && detail[key] !== '') {
      parts.push(`${key}=${String(detail[key])}`)
    }
  }
  return parts.join(' · ')
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
