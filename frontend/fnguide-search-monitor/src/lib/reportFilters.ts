import type { ReportSort } from '../hooks/useReports'

export const STATUS_FILTERS = [
  'all',
  'downloaded',
  'blind',
  'listed',
  'no_download',
  'failed',
] as const

export type StatusFilter = (typeof STATUS_FILTERS)[number]

/** null = 기본 정렬(최근)이지만 UI상 선택 없음 */
export type ReportSortChoice = ReportSort | null

export type ReportFilters = {
  status: StatusFilter
  q: string
  sort: ReportSortChoice
  offset: number
}

export const DEFAULT_REPORT_FILTERS: ReportFilters = {
  status: 'all',
  q: '',
  sort: null,
  offset: 0,
}

/** API/목록 조회에 쓰는 실제 정렬 (미선택이면 최근순) */
export function resolveReportSort(sort: ReportSortChoice): ReportSort {
  return sort ?? 'last_seen_at'
}

function isStatusFilter(value: string): value is StatusFilter {
  return (STATUS_FILTERS as readonly string[]).includes(value)
}

function isReportSort(value: string): value is ReportSort {
  return (
    value === 'published_at' ||
    value === 'page_count' ||
    value === 'last_seen_at'
  )
}

/** URLSearchParams → 필터 상태 */
export function parseReportFilters(params: URLSearchParams): ReportFilters {
  const rawStatus = params.get('status') || 'all'
  const rawSort = params.get('sort')
  const rawOffset = Number(params.get('offset') || '0')
  return {
    status: isStatusFilter(rawStatus) ? rawStatus : 'all',
    q: params.get('q') || '',
    sort: rawSort && isReportSort(rawSort) ? rawSort : null,
    offset: Number.isFinite(rawOffset) ? Math.max(0, rawOffset) : 0,
  }
}

/** 필터 상태 → URLSearchParams (기본값은 키 자체를 생략) */
export function serializeReportFilters(filters: ReportFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.status !== 'all') params.set('status', filters.status)
  const q = filters.q.trim()
  if (q) params.set('q', q)
  if (filters.sort) params.set('sort', filters.sort)
  if (filters.offset > 0) params.set('offset', String(filters.offset))
  return params
}

export function isReportFiltersDirty(
  filters: ReportFilters,
  draftQ?: string,
): boolean {
  if (filters.status !== DEFAULT_REPORT_FILTERS.status) return true
  if (filters.q.trim() !== DEFAULT_REPORT_FILTERS.q) return true
  if (filters.sort !== DEFAULT_REPORT_FILTERS.sort) return true
  if (filters.offset !== DEFAULT_REPORT_FILTERS.offset) return true
  if (draftQ !== undefined && draftQ.trim() !== filters.q.trim()) return true
  return false
}

/** 활성 칩을 다시 누르면 전체로 */
export function withStatus(
  filters: ReportFilters,
  status: StatusFilter,
): ReportFilters {
  const next =
    status === 'all' || status === filters.status ? 'all' : status
  return { ...filters, status: next, offset: 0 }
}

/** 같은 정렬을 다시 누르면 선택 해제(기본 정렬로, 다른 열은 켜지지 않음) */
export function withSort(
  filters: ReportFilters,
  sort: ReportSort,
): ReportFilters {
  const next: ReportSortChoice = filters.sort === sort ? null : sort
  return { ...filters, sort: next, offset: 0 }
}

export function withQuery(filters: ReportFilters, q: string): ReportFilters {
  return { ...filters, q: q.trim(), offset: 0 }
}

export function withPage(
  filters: ReportFilters,
  delta: number,
  pageSize: number,
): ReportFilters {
  return {
    ...filters,
    offset: Math.max(0, filters.offset + delta * pageSize),
  }
}

export function resetReportFilters(): ReportFilters {
  return { ...DEFAULT_REPORT_FILTERS }
}
