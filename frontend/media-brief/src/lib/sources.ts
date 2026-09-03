import type { MediaSource, NewsSource, ReportMediaSource } from '../types'

export const PER_SOURCE_LIMIT = 8

export const NEWS_SOURCES: NewsSource[] = ['arg', 'nikkei', 'google_news']
export const REPORT_SOURCES: ReportMediaSource[] = ['hbr', 'hbrkorea']

export const MEDIA_SOURCES: MediaSource[] = [
  ...NEWS_SOURCES,
  ...REPORT_SOURCES,
]

export const SOURCE_LABEL: Record<MediaSource, string> = {
  arg: 'ARG',
  nikkei: 'Nikkei',
  google_news: 'Google News',
  hbr: 'HBR',
  hbrkorea: 'HBR Korea',
}

export function isNewsSource(source: MediaSource): source is NewsSource {
  return (NEWS_SOURCES as string[]).includes(source)
}
