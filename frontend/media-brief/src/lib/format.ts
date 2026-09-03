const KST = 'Asia/Seoul'
const DATE_ONLY_RE = /^\d{4}-\d{2}-\d{2}$/

export function formatPublishedAt(value: string | null | undefined): string {
  if (!value) return '—'
  const trimmed = value.trim()
  // Reports DATE: do not parse as UTC midnight (would shift in western TZs).
  if (DATE_ONLY_RE.test(trimmed)) return trimmed
  const d = new Date(trimmed)
  if (Number.isNaN(d.getTime())) return value
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: KST,
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(d)
}

export function truncate(text: string, max = 180): string {
  const t = text.trim()
  if (t.length <= max) return t
  return `${t.slice(0, max - 1)}…`
}
