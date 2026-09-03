import { useCallback, useEffect, useState } from 'react'
import type { PeriodRange } from '../lib/period'
import { PER_SOURCE_LIMIT, NEWS_SOURCES, REPORT_SOURCES } from '../lib/sources'
import type {
  BriefArticle,
  MediaSource,
  NewsArticleRecord,
  NewsArticlesResponse,
  NewsSource,
  ReportMediaSource,
  ReportRecord,
  ReportsResponse,
} from '../types'

export type SourceBucket = {
  source: MediaSource
  items: BriefArticle[]
  total: number
  error: string | null
}

function newsSnippet(row: NewsArticleRecord): string | null {
  const snippet = row.snippet?.trim()
  if (snippet) return snippet
  const body = row.body_text?.trim()
  if (body) return body.slice(0, 280)
  return null
}

function mapNews(row: NewsArticleRecord, source: NewsSource): BriefArticle {
  return {
    id: String(row.id),
    source,
    title: (row.title || '').trim() || '(제목 없음)',
    titleKo: row.title_ko?.trim() || null,
    url: row.url?.trim() || null,
    publishedAt: row.published_at ?? null,
    section: row.section || row.publisher || null,
    snippet: newsSnippet(row),
    lane: 'news',
  }
}

function mapReport(row: ReportRecord, source: ReportMediaSource): BriefArticle {
  const qj = row.quality_json ?? {}
  const shortTitle =
    typeof qj.short_title === 'string' ? qj.short_title.trim() : ''
  const summary = typeof qj.summary === 'string' ? qj.summary.trim() : ''
  return {
    id: String(row.id),
    source,
    title: (row.title || shortTitle || '').trim() || '(제목 없음)',
    titleKo: shortTitle && shortTitle !== row.title ? shortTitle : null,
    url: row.url?.trim() || null,
    publishedAt: row.published_at ?? null,
    section: row.provider || null,
    snippet: summary || null,
    lane: 'report',
  }
}

async function fetchNewsSource(
  source: NewsSource,
  range: PeriodRange,
  signal: AbortSignal,
): Promise<{ items: BriefArticle[]; total: number }> {
  const qs = new URLSearchParams({
    source,
    has_body: 'yes',
    limit: String(PER_SOURCE_LIMIT),
    offset: '0',
    published_from: range.from,
    published_to: range.to,
  })
  let res = await fetch(`/api/news-articles?${qs}`, { signal })
  let data = (await res.json()) as NewsArticlesResponse
  if (!res.ok || !data.ok) {
    throw new Error(data.message || `news ${source}: HTTP ${res.status}`)
  }
  // Fallback: period items without requiring body.
  if (data.items.length === 0) {
    qs.set('has_body', 'all')
    res = await fetch(`/api/news-articles?${qs}`, { signal })
    data = (await res.json()) as NewsArticlesResponse
    if (!res.ok || !data.ok) {
      throw new Error(data.message || `news ${source}: HTTP ${res.status}`)
    }
  }
  return {
    items: data.items.map((row) => mapNews(row, source)),
    total: data.total,
  }
}

async function fetchReportSource(
  source: ReportMediaSource,
  range: PeriodRange,
  signal: AbortSignal,
): Promise<{ items: BriefArticle[]; total: number }> {
  const base = {
    source,
    sort: 'published_at',
    limit: String(PER_SOURCE_LIMIT),
    offset: '0',
    published_from: range.from,
    published_to: range.to,
  }
  const passQs = new URLSearchParams({ ...base, quality: 'pass' })
  let res = await fetch(`/api/reports?${passQs}`, { signal })
  let data = (await res.json()) as ReportsResponse
  if (!res.ok || !data.ok) {
    throw new Error(data.message || `reports ${source}: HTTP ${res.status}`)
  }
  if (data.items.length === 0) {
    const allQs = new URLSearchParams({ ...base, quality: 'all' })
    res = await fetch(`/api/reports?${allQs}`, { signal })
    data = (await res.json()) as ReportsResponse
    if (!res.ok || !data.ok) {
      throw new Error(data.message || `reports ${source}: HTTP ${res.status}`)
    }
  }
  return {
    items: data.items.map((row) => mapReport(row, source)),
    total: data.total,
  }
}

export function useMediaBrief(range: PeriodRange | null) {
  const [buckets, setBuckets] = useState<SourceBucket[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  const reload = useCallback(() => {
    setReloadToken((n) => n + 1)
  }, [])

  useEffect(() => {
    if (!range) {
      setBuckets([])
      setLoading(false)
      setError(null)
      return
    }

    const ac = new AbortController()
    setLoading(true)
    setError(null)

    async function run() {
      const newsJobs = NEWS_SOURCES.map(async (source) => {
        try {
          const { items, total } = await fetchNewsSource(
            source,
            range!,
            ac.signal,
          )
          return {
            source,
            items,
            total,
            error: null,
          } satisfies SourceBucket
        } catch (e) {
          if (ac.signal.aborted) throw e
          return {
            source,
            items: [],
            total: 0,
            error: e instanceof Error ? e.message : String(e),
          } satisfies SourceBucket
        }
      })

      const reportJobs = REPORT_SOURCES.map(async (source) => {
        try {
          const { items, total } = await fetchReportSource(
            source,
            range!,
            ac.signal,
          )
          return {
            source,
            items,
            total,
            error: null,
          } satisfies SourceBucket
        } catch (e) {
          if (ac.signal.aborted) throw e
          return {
            source,
            items: [],
            total: 0,
            error: e instanceof Error ? e.message : String(e),
          } satisfies SourceBucket
        }
      })

      try {
        const results = await Promise.all([...newsJobs, ...reportJobs])
        if (ac.signal.aborted) return
        const order = [...NEWS_SOURCES, ...REPORT_SOURCES]
        results.sort(
          (a, b) => order.indexOf(a.source) - order.indexOf(b.source),
        )
        setBuckets(results)
        const hard = results.filter((r) => r.error).length === results.length
        setError(hard ? '모든 매체 조회에 실패했습니다.' : null)
      } catch {
        if (!ac.signal.aborted) {
          setError('조회 중 오류가 발생했습니다.')
          setBuckets([])
        }
      } finally {
        if (!ac.signal.aborted) setLoading(false)
      }
    }

    void run()
    return () => ac.abort()
  }, [range, reloadToken])

  return { buckets, loading, error, reload }
}
