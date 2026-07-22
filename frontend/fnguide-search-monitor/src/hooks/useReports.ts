import { useCallback, useEffect, useState } from 'react'
import type { ReportCounts, ReportRecord, ReportsResponse } from '../types'

const POLL_MS = 15_000

const EMPTY_COUNTS: ReportCounts = {
  all: 0,
  listed: 0,
  blind: 0,
  downloaded: 0,
  no_download: 0,
  failed: 0,
}

export type ReportSort = 'published_at' | 'page_count' | 'last_seen_at'

export type ReportsQuery = {
  status?: string
  q?: string
  crawlId?: string | null
  sort?: ReportSort
  limit?: number
  offset?: number
  poll?: boolean
}

export type ReportsView = {
  items: ReportRecord[]
  total: number
  counts: ReportCounts
  limit: number
  offset: number
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useReports(query: ReportsQuery): ReportsView {
  const status = query.status && query.status !== 'all' ? query.status : ''
  const q = query.q?.trim() || ''
  const crawlId = query.crawlId || ''
  const sort: ReportSort =
    query.sort === 'published_at' || query.sort === 'page_count'
      ? query.sort
      : 'last_seen_at'
  const limit = query.limit ?? 30
  const offset = query.offset ?? 0
  const poll = query.poll !== false

  const [items, setItems] = useState<ReportRecord[]>([])
  const [total, setTotal] = useState(0)
  const [counts, setCounts] = useState<ReportCounts>(EMPTY_COUNTS)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    const params = new URLSearchParams()
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    if (status) params.set('status', status)
    if (q) params.set('q', q)
    if (crawlId) params.set('crawl_id', crawlId)
    if (sort !== 'last_seen_at') params.set('sort', sort)
    try {
      const res = await fetch(`/api/reports?${params}`)
      const data = (await res.json()) as ReportsResponse
      if (!res.ok) {
        throw new Error(data.message || `HTTP ${res.status}`)
      }
      setItems(data.items ?? [])
      setTotal(data.total ?? 0)
      setCounts({ ...EMPTY_COUNTS, ...(data.counts || {}) })
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'fetch failed')
    } finally {
      setLoading(false)
    }
  }, [status, q, crawlId, sort, limit, offset])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void refresh().then(() => {
      if (cancelled) return
    })
    if (!poll) {
      return () => {
        cancelled = true
      }
    }
    const id = window.setInterval(() => {
      void refresh()
    }, POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [refresh, poll])

  return {
    items,
    total,
    counts,
    limit,
    offset,
    loading,
    error,
    refresh,
  }
}
