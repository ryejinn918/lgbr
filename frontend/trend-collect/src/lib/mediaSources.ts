/**
 * Adhoc media sources — keep in sync with crawler.sources.registry
 * and api lgbr_api.source_registry.
 */
export type MediaSource = {
  id: string
  label: string
  hubUrl: string
  hasSearch: boolean
  hasCatalogs: boolean
  /** Account login before CDP hold (FnGuide-style). */
  requiresLogin?: boolean
  loginUrl?: string
}

export const MEDIA_SOURCES: MediaSource[] = [
  {
    id: 'pwc',
    label: 'PwC',
    hubUrl: 'https://www.pwc.com/kr/ko/insights.html',
    hasSearch: true,
    hasCatalogs: true,
  },
  {
    id: 'accenture',
    label: 'Accenture',
    hubUrl: 'https://www.accenture.com/us-en/insights',
    hasSearch: true,
    hasCatalogs: false,
  },
  {
    id: 'kpmg',
    label: 'KPMG',
    hubUrl: 'https://kpmg.com/us/en/insights-and-resources.html',
    hasSearch: true,
    hasCatalogs: false,
  },
  {
    id: 'ey',
    label: 'EY',
    hubUrl: 'https://www.ey.com/en_us/insights',
    hasSearch: true,
    hasCatalogs: false,
  },
  {
    id: 'deloitte',
    label: 'Deloitte',
    hubUrl: 'https://www.deloitte.com/us/en/insights.html',
    hasSearch: true,
    hasCatalogs: false,
  },
  {
    id: 'mckinsey',
    label: 'McKinsey',
    hubUrl: 'https://www.mckinsey.com/',
    hasSearch: false,
    hasCatalogs: false,
  },
  {
    id: 'bain',
    label: 'Bain',
    hubUrl: 'https://www.bain.com/',
    hasSearch: true,
    hasCatalogs: false,
  },
  {
    id: 'hbrkorea',
    label: 'HBR Korea',
    hubUrl: 'https://www.hbrkorea.com/',
    hasSearch: true,
    hasCatalogs: false,
    requiresLogin: true,
    loginUrl: 'https://www.hbrkorea.com/member/login',
  },
  {
    id: 'nikkei',
    label: 'Nikkei',
    hubUrl: 'https://www.nikkei.com/',
    hasSearch: false,
    hasCatalogs: false,
    requiresLogin: true,
    loginUrl: 'https://www.nikkei.com/login',
  },
  {
    id: 'nikkeixtech',
    label: 'Nikkei xTECH',
    hubUrl: 'https://xtech.nikkei.com/',
    hasSearch: false,
    hasCatalogs: false,
    requiresLogin: true,
    loginUrl:
      'https://bpsso.nikkei.com/ep/auth/prev/?ts=nxt&ru=' +
      'https%3A%2F%2Fbpsso.nikkei.com%2Fep%2Fcookie%2F%3Fru%3D' +
      'https%253A%252F%252Fxtech.nikkei.com%252F',
  },
]

export type MediaSourceId = (typeof MEDIA_SOURCES)[number]['id']

const BY_ID = new Map(MEDIA_SOURCES.map((s) => [s.id, s]))

export function getMediaSource(id: string | null | undefined): MediaSource | null {
  if (!id) return null
  return BY_ID.get(id) ?? null
}

export function isMediaSourceId(id: string | null | undefined): id is MediaSourceId {
  return !!id && BY_ID.has(id)
}

/** Crawl modes owned by media adhoc (not FnGuide). */
export function isMediaAdhocMode(mode: string | null | undefined): boolean {
  return isMediaSourceId(mode)
}
