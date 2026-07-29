/** PwC list catalogs (목록 타입) — mirrors crawler.sources.pwc_http.CATALOGS */

export type PwcCatalogId = 'kr' | 'gx'

export type PwcCatalog = {
  id: PwcCatalogId
  label: string
  hubUrl: string
  pageSize: number
  note: string
}

export const PWC_CATALOGS: PwcCatalog[] = [
  {
    id: 'kr',
    label: '한국 (삼일)',
    hubUrl: 'https://www.pwc.com/kr/ko/insights.html',
    pageSize: 16,
    note: '삼일PwC Insights 목록',
  },
  {
    id: 'gx',
    label: '국제',
    hubUrl: 'https://www.pwc.com/gx/en/research-insights.html',
    pageSize: 8,
    note: 'PwC Global Research & Insights',
  },
]

export const DEFAULT_PWC_CATALOG: PwcCatalogId = 'kr'

export function getPwcCatalog(id: string | null | undefined): PwcCatalog {
  const key = (id || DEFAULT_PWC_CATALOG).trim().toLowerCase()
  return (
    PWC_CATALOGS.find((c) => c.id === key) ??
    PWC_CATALOGS.find((c) => c.id === DEFAULT_PWC_CATALOG)!
  )
}
