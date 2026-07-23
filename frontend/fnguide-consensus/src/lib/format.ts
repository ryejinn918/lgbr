import { labelStage } from './labels'

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

export function formatEventDetail(detail: Record<string, unknown>): string {
  try {
    return JSON.stringify(detail)
  } catch {
    return String(detail)
  }
}
