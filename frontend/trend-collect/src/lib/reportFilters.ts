import type { ReportSort } from '../hooks/useReports'
import { REPORT_THEMES } from './themes'

export const STATUS_FILTERS = [
  'all',
  'downloaded',
  'blind',
  'listed',
  'no_download',
  'failed',
] as const

export const QUALITY_FILTERS = [
  'all',
  'pass',
  'fail',
  'pending',
  'unauditable',
] as const

export const THEME_FILTERS = ['all', ...REPORT_THEMES, 'other'] as const

export type StatusFilter = (typeof STATUS_FILTERS)[number]
export type QualityFilter = (typeof QUALITY_FILTERS)[number]
export type ThemeFilter = (typeof THEME_FILTERS)[number]

/** null = 기본 정렬(발행일 내림)이지만 UI상 화살표 없음 */
export type ReportSortChoice = ReportSort | null
export type ReportSortDir = 'asc' | 'desc'

export type ReportFilters = {
  status: StatusFilter
  quality: QualityFilter
  theme: ThemeFilter
  q: string
  sort: ReportSortChoice
  sortDir: ReportSortDir
  offset: number
}

export const DEFAULT_REPORT_FILTERS: ReportFilters = {
  status: 'all',
  quality: 'all',
  theme: 'all',
  q: '',
  sort: null,
  sortDir: 'desc',
  offset: 0,
}

/** API/목록 조회에 쓰는 실제 정렬 (미선택이면 발행일순) */
export function resolveReportSort(sort: ReportSortChoice): ReportSort {
  return sort ?? 'published_at'
}

export function resolveReportSortDir(filters: ReportFilters): ReportSortDir {
  return filters.sortDir === 'asc' ? 'asc' : 'desc'
}

function isStatusFilter(value: string): value is StatusFilter {
  return (STATUS_FILTERS as readonly string[]).includes(value)
}

function isQualityFilter(value: string): value is QualityFilter {
  return (QUALITY_FILTERS as readonly string[]).includes(value)
}

function isThemeFilter(value: string): value is ThemeFilter {
  return (THEME_FILTERS as readonly string[]).includes(value)
}

function isReportSort(value: string): value is ReportSort {
  return (
    value === 'published_at' ||
    value === 'page_count' ||
    value === 'last_seen_at'
  )
}

function isReportSortDir(value: string): value is ReportSortDir {
  return value === 'asc' || value === 'desc'
}

/** URLSearchParams → 필터 상태 */
export function parseReportFilters(params: URLSearchParams): ReportFilters {
  const rawStatus = params.get('status') || 'all'
  const rawQuality = params.get('quality') || 'all'
  const rawTheme = params.get('theme') || 'all'
  const rawSort = params.get('sort')
  const rawDir = params.get('dir')
  const rawOffset = Number(params.get('offset') || '0')
  const sort = rawSort && isReportSort(rawSort) ? rawSort : null
  const sortDir =
    sort && rawDir && isReportSortDir(rawDir) ? rawDir : 'desc'
  return {
    status: isStatusFilter(rawStatus) ? rawStatus : 'all',
    quality: isQualityFilter(rawQuality) ? rawQuality : 'all',
    theme: isThemeFilter(rawTheme) ? rawTheme : 'all',
    q: params.get('q') || '',
    sort,
    sortDir,
    offset: Number.isFinite(rawOffset) ? Math.max(0, rawOffset) : 0,
  }
}

/** 필터 상태 → URLSearchParams (기본값은 키 자체를 생략) */
export function serializeReportFilters(filters: ReportFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.status !== 'all') params.set('status', filters.status)
  if (filters.quality !== 'all') params.set('quality', filters.quality)
  if (filters.theme !== 'all') params.set('theme', filters.theme)
  const q = filters.q.trim()
  if (q) params.set('q', q)
  if (filters.sort) {
    params.set('sort', filters.sort)
    if (filters.sortDir === 'asc') params.set('dir', 'asc')
  }
  if (filters.offset > 0) params.set('offset', String(filters.offset))
  return params
}

export function isReportFiltersDirty(
  filters: ReportFilters,
  draftQ?: string,
): boolean {
  if (filters.status !== DEFAULT_REPORT_FILTERS.status) return true
  if (filters.quality !== DEFAULT_REPORT_FILTERS.quality) return true
  if (filters.theme !== DEFAULT_REPORT_FILTERS.theme) return true
  if (filters.q.trim() !== DEFAULT_REPORT_FILTERS.q) return true
  if (filters.sort !== DEFAULT_REPORT_FILTERS.sort) return true
  if (filters.sortDir !== DEFAULT_REPORT_FILTERS.sortDir) return true
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

export function withQuality(
  filters: ReportFilters,
  quality: QualityFilter,
): ReportFilters {
  const next =
    quality === 'all' || quality === filters.quality ? 'all' : quality
  return { ...filters, quality: next, offset: 0 }
}

export function withTheme(
  filters: ReportFilters,
  theme: ThemeFilter,
): ReportFilters {
  const next = theme === 'all' || theme === filters.theme ? 'all' : theme
  return { ...filters, theme: next, offset: 0 }
}

/**
 * 다른 열 → 그 열 내림차순(명시).
 * 같은 열 → 오름/내림 토글. 발행일+내림이면 기본(null)으로 정규화.
 */
export function withSort(
  filters: ReportFilters,
  sort: ReportSort,
): ReportFilters {
  if (filters.sort === sort) {
    const nextDir: ReportSortDir =
      filters.sortDir === 'asc' ? 'desc' : 'asc'
    if (sort === 'published_at' && nextDir === 'desc') {
      return { ...filters, sort: null, sortDir: 'desc', offset: 0 }
    }
    return { ...filters, sort, sortDir: nextDir, offset: 0 }
  }
  return { ...filters, sort, sortDir: 'desc', offset: 0 }
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

/** 다운됨 + pending(미검사/미요약/미완료) 프리셋 */
export function unauditedPreset(filters?: ReportFilters): ReportFilters {
  return {
    ...(filters ?? DEFAULT_REPORT_FILTERS),
    status: 'downloaded',
    quality: 'pending',
    offset: 0,
  }
}

export function isUnauditedPreset(filters: ReportFilters): boolean {
  return filters.status === 'downloaded' && filters.quality === 'pending'
}
