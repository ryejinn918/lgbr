export type PeriodPreset = '7d' | '30d' | '90d' | 'custom'

export type PeriodRange = {
  from: string
  to: string
}

const PRESET_DAYS: Record<Exclude<PeriodPreset, 'custom'>, number> = {
  '7d': 7,
  '30d': 30,
  '90d': 90,
}

/** Local calendar date as YYYY-MM-DD. */
export function toDateInputValue(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function startOfLocalDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0)
}

function addDays(d: Date, days: number): Date {
  const next = new Date(d)
  next.setDate(next.getDate() + days)
  return next
}

/** Exclusive upper bound: start of tomorrow (local). */
export function defaultPublishedTo(): string {
  return startOfLocalDay(addDays(new Date(), 1)).toISOString()
}

export function rangeFromPreset(
  preset: Exclude<PeriodPreset, 'custom'>,
): PeriodRange {
  const days = PRESET_DAYS[preset]
  const to = startOfLocalDay(addDays(new Date(), 1))
  const from = startOfLocalDay(addDays(to, -days))
  return { from: from.toISOString(), to: to.toISOString() }
}

/** Custom inclusive calendar dates → API bounds (to exclusive = next day). */
export function rangeFromCustomDates(
  fromDate: string,
  toDate: string,
): PeriodRange | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(fromDate) || !/^\d{4}-\d{2}-\d{2}$/.test(toDate)) {
    return null
  }
  const from = startOfLocalDay(new Date(`${fromDate}T00:00:00`))
  const toInclusive = startOfLocalDay(new Date(`${toDate}T00:00:00`))
  if (Number.isNaN(from.getTime()) || Number.isNaN(toInclusive.getTime())) {
    return null
  }
  if (from > toInclusive) return null
  const to = addDays(toInclusive, 1)
  return { from: from.toISOString(), to: to.toISOString() }
}

export function formatPeriodLabel(range: PeriodRange): string {
  const from = new Date(range.from)
  const toExclusive = new Date(range.to)
  const toInclusive = addDays(toExclusive, -1)
  return `${toDateInputValue(from)} ~ ${toDateInputValue(toInclusive)}`
}
