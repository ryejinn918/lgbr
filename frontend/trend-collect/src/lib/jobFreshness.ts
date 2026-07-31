export type FreshnessKind = 'report' | 'daily' | 'article'
export type FreshnessGrade = 'fresh' | 'aging' | 'stale'

const DAY_MS = 86_400_000

/** Report: weekly–monthly. Daily/article news lanes: tighter. */
const THRESHOLDS: Record<
  FreshnessKind,
  { freshMs: number; agingMs: number }
> = {
  report: { freshMs: 7 * DAY_MS, agingMs: 30 * DAY_MS },
  daily: { freshMs: 2 * DAY_MS, agingMs: 7 * DAY_MS },
  article: { freshMs: 2 * DAY_MS, agingMs: 7 * DAY_MS },
}

export function freshnessGrade(
  iso: string | null | undefined,
  kind: FreshnessKind,
): FreshnessGrade {
  if (!iso) return 'stale'
  const ms = Date.parse(iso)
  if (Number.isNaN(ms)) return 'stale'
  const age = Date.now() - ms
  if (age < 0) return 'fresh'
  const t = THRESHOLDS[kind]
  if (age < t.freshMs) return 'fresh'
  if (age < t.agingMs) return 'aging'
  return 'stale'
}

export function freshnessClass(
  iso: string | null | undefined,
  kind: FreshnessKind,
): string {
  return `fresh-${freshnessGrade(iso, kind)}`
}

/** Prefer job/crawl timestamp; fall back to newest document seen. */
export function pickFreshnessAt(
  lastCollectedAt: string | null | undefined,
  lastDocAt?: string | null | undefined,
): string | null {
  return lastCollectedAt || lastDocAt || null
}
