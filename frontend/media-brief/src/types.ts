export type NewsSource = 'arg' | 'nikkei' | 'google_news'
export type ReportMediaSource = 'hbr' | 'hbrkorea'
export type MediaSource = NewsSource | ReportMediaSource

export type BriefArticle = {
  id: string
  source: MediaSource
  title: string
  titleKo: string | null
  url: string | null
  publishedAt: string | null
  section: string | null
  snippet: string | null
  lane: 'news' | 'report'
}

export type NewsArticleRecord = {
  id: string
  source: string
  title: string | null
  title_ko?: string | null
  snippet?: string | null
  url?: string | null
  published_at?: string | null
  publisher?: string | null
  section?: string | null
  body_text?: string | null
  has_body?: boolean
  attrs?: Record<string, unknown>
}

export type NewsArticlesResponse = {
  ok: boolean
  message?: string
  items: NewsArticleRecord[]
  total: number
}

export type ReportRecord = {
  id: string
  source: string
  title: string | null
  url?: string | null
  published_at?: string | null
  provider?: string | null
  quality?: string
  quality_json?: {
    short_title?: string
    summary?: string
    [key: string]: unknown
  }
}

export type ReportsResponse = {
  ok: boolean
  message?: string
  items: ReportRecord[]
  total: number
}
