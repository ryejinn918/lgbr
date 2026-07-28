import { labelEvent, labelStage } from './labels'

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function formatProgress(progress: Record<string, unknown>): string {
  const stage = progress.stage != null ? labelStage(String(progress.stage)) : ''
  const done = progress.docs_done
  const total = progress.docs_total
  const parts: string[] = []
  if (stage) parts.push(stage)
  if (done != null && total != null) parts.push(`${done}/${total}`)
  return parts.join(' · ') || '—'
}

const DETAIL_KEYS: { key: string; label: string }[] = [
  { key: 'core', label: '중심축' },
  { key: 'bibliography', label: '참고' },
  { key: 'selected', label: '선별' },
  { key: 'excluded', label: '제외' },
  { key: 'reports', label: '보고서' },
  { key: 'count', label: '건수' },
  { key: 'chars', label: '글자' },
  { key: 'docs_done', label: '완료' },
  { key: 'docs_failed', label: '실패' },
  { key: 'docs_total', label: '전체' },
  { key: 'error', label: '오류' },
]

export function formatEventDetail(detail: Record<string, unknown>): string {
  if (!detail || typeof detail !== 'object') return ''
  const parts: string[] = []
  for (const { key, label } of DETAIL_KEYS) {
    const v = detail[key]
    if (v == null || v === '') continue
    if (typeof v === 'object') continue
    parts.push(`${label} ${String(v)}`)
  }
  return parts.join(' · ')
}

export function formatEventLine(stage: string, event: string): string {
  const s = labelStage(stage)
  const e = labelEvent(event)
  if (!stage) return e
  if (e === event && s !== stage) return `${s} · ${e}`
  if (e === '시작' || e === '끝') return `${s} ${e}`
  return e === event ? `${s} · ${e}` : e
}
