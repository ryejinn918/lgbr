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
