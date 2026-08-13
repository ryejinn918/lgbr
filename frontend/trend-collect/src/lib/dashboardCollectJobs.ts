import { DEFAULT_BCG_PROFILE } from './bcgProfiles'
import { DEFAULT_DELOITTE_PROFILE } from './deloitteProfiles'
import type { FreshnessKind } from './jobFreshness'
import { DEFAULT_NIKKEI_SECTION } from './nikkeiSections'
import { DEFAULT_PWC_CATALOG } from './pwcCatalogs'

export type DashboardCollectJobKind =
  | 'fnguide_all_profiles'
  | 'collection_search'
  | 'collection_feed'
  | 'collection_fetch_body'

export type DashboardCollectJobDef = {
  key: string
  source: string
  title: string
  jobLabel: string
  settingsPath: string
  docsPath: string
  freshnessKind: FreshnessKind
  kind: DashboardCollectJobKind
  /** collection API capability when kind is collection_* */
  capability?: 'search' | 'feed' | 'fetch_body'
}

/** Dashboard「수집 작업」rows — source × default job. */
export const DASHBOARD_COLLECT_JOBS: DashboardCollectJobDef[] = [
  {
    key: 'fnguide:search',
    source: 'fnguide',
    title: 'FnGuide',
    jobLabel: '검색',
    settingsPath: '/collect/fnguide/list/search',
    docsPath: '/docs/reports/fnguide',
    freshnessKind: 'report',
    kind: 'fnguide_all_profiles',
  },
  {
    key: 'pwc:search',
    source: 'pwc',
    title: 'PwC',
    jobLabel: '검색',
    settingsPath: '/collect/pwc/list/search',
    docsPath: '/docs/reports/pwc',
    freshnessKind: 'report',
    kind: 'collection_search',
    capability: 'search',
  },
  {
    key: 'accenture:search',
    source: 'accenture',
    title: 'Accenture',
    jobLabel: '검색',
    settingsPath: '/collect/accenture/list/search',
    docsPath: '/docs/reports/accenture',
    freshnessKind: 'report',
    kind: 'collection_search',
    capability: 'search',
  },
  {
    key: 'kpmg:search',
    source: 'kpmg',
    title: 'KPMG',
    jobLabel: '검색',
    settingsPath: '/collect/kpmg/list/search',
    docsPath: '/docs/reports/kpmg',
    freshnessKind: 'report',
    kind: 'collection_search',
    capability: 'search',
  },
  {
    key: 'ey:search',
    source: 'ey',
    title: 'EY',
    jobLabel: '검색',
    settingsPath: '/collect/ey/list/search',
    docsPath: '/docs/reports/ey',
    freshnessKind: 'report',
    kind: 'collection_search',
    capability: 'search',
  },
  {
    key: 'deloitte:search',
    source: 'deloitte',
    title: 'Deloitte',
    jobLabel: '검색',
    settingsPath: '/collect/deloitte/list/search',
    docsPath: '/docs/reports/deloitte',
    freshnessKind: 'report',
    kind: 'collection_search',
    capability: 'search',
  },
  {
    key: 'bain:search',
    source: 'bain',
    title: 'Bain',
    jobLabel: '검색',
    settingsPath: '/collect/bain/list/search',
    docsPath: '/docs/reports/bain',
    freshnessKind: 'report',
    kind: 'collection_search',
    capability: 'search',
  },
  {
    key: 'bcg:search',
    source: 'bcg',
    title: 'BCG',
    jobLabel: '검색',
    settingsPath: '/collect/bcg/list/search',
    docsPath: '/docs/reports/bcg',
    freshnessKind: 'report',
    kind: 'collection_search',
    capability: 'search',
  },
  {
    key: 'hbr:search',
    source: 'hbr',
    title: 'HBR',
    jobLabel: '검색',
    settingsPath: '/collect/hbr/list/search',
    docsPath: '/docs/reports/hbr',
    freshnessKind: 'report',
    kind: 'collection_search',
    capability: 'search',
  },
  {
    key: 'hbrkorea:search',
    source: 'hbrkorea',
    title: 'HBR Korea',
    jobLabel: '검색',
    settingsPath: '/collect/hbrkorea/list/search',
    docsPath: '/docs/reports/hbrkorea',
    freshnessKind: 'report',
    kind: 'collection_search',
    capability: 'search',
  },
  {
    key: 'arg:feed',
    source: 'arg',
    title: 'ARG',
    jobLabel: '피드',
    settingsPath: '/collect/arg/list/feed',
    docsPath: '/docs/articles?source=arg',
    freshnessKind: 'daily',
    kind: 'collection_feed',
    capability: 'feed',
  },
  {
    key: 'nikkei:feed',
    source: 'nikkei',
    title: 'Nikkei',
    jobLabel: '피드',
    settingsPath: '/collect/nikkei/list/feed',
    docsPath: '/docs/articles?source=nikkei',
    freshnessKind: 'daily',
    kind: 'collection_feed',
    capability: 'feed',
  },
  {
    key: 'nikkei:body',
    source: 'nikkei',
    title: 'Nikkei',
    jobLabel: '본문',
    settingsPath: '/collect/nikkei/body/fetch',
    docsPath: '/docs/articles?source=nikkei',
    freshnessKind: 'daily',
    kind: 'collection_fetch_body',
    capability: 'fetch_body',
  },
]

/** Defaults aligned with Collect RunPage initial state. */
export type DashboardStartArgs = {
  mode?: 'all_profiles'
  maxPages?: number
  periodMonths?: number
  limit?: number
  catalog?: string
  profile?: string
  itemDelaySeconds?: number
  delaySeconds?: number
  section?: string
}

export function startArgsForJob(key: string): DashboardStartArgs {
  switch (key) {
    case 'fnguide:search':
      return { mode: 'all_profiles' }
    case 'pwc:search':
      return {
        maxPages: 20,
        periodMonths: 3,
        catalog: DEFAULT_PWC_CATALOG,
        itemDelaySeconds: 2,
      }
    case 'accenture:search':
      return {
        maxPages: 20,
        periodMonths: 3,
        catalog: 'us',
        itemDelaySeconds: 2,
      }
    case 'kpmg:search':
      return { maxPages: 20, periodMonths: 3, itemDelaySeconds: 2 }
    case 'ey:search':
      return { maxPages: 20, periodMonths: 3, itemDelaySeconds: 2 }
    case 'deloitte:search':
      return {
        maxPages: 20,
        periodMonths: 3,
        profile: DEFAULT_DELOITTE_PROFILE,
        itemDelaySeconds: 2,
      }
    case 'bain:search':
      return {
        maxPages: 20,
        periodMonths: 3,
        catalog: 'us',
        itemDelaySeconds: 5,
      }
    case 'bcg:search':
      return {
        maxPages: 10,
        periodMonths: 3,
        profile: DEFAULT_BCG_PROFILE,
        itemDelaySeconds: 2,
      }
    case 'hbr:search':
      return { maxPages: 10, periodMonths: 3, itemDelaySeconds: 5 }
    case 'hbrkorea:search':
      return { maxPages: 10, periodMonths: 3, itemDelaySeconds: 5 }
    case 'arg:feed':
      return { maxPages: 50, periodMonths: 3 }
    case 'nikkei:feed':
      return {
        maxPages: 1,
        periodMonths: 3,
        section: DEFAULT_NIKKEI_SECTION,
      }
    case 'nikkei:body':
      return { limit: 50, delaySeconds: 1.5 }
    default:
      return {}
  }
}

export function startConfirmLabel(def: DashboardCollectJobDef): string {
  const args = startArgsForJob(def.key)
  if (def.kind === 'fnguide_all_profiles') {
    return `${def.title} · 프로필 전체 순차`
  }
  if (def.kind === 'collection_fetch_body') {
    return `${def.title} · ${def.jobLabel} · 최대 ${args.limit ?? 50}건`
  }
  if (def.kind === 'collection_feed') {
    const section = args.section ? ` · ${args.section}` : ''
    return `${def.title} · ${def.jobLabel}${section} · ${args.periodMonths ?? 3}개월`
  }
  const catalog = args.catalog ? ` · ${args.catalog}` : ''
  const profile = args.profile ? ` · ${args.profile}` : ''
  return `${def.title} · ${def.jobLabel}${catalog}${profile} · ${args.periodMonths ?? 3}개월 · ${args.maxPages ?? 20}p`
}
