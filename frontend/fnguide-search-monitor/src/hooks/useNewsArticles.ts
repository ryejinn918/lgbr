import { useEffect, useState } from 'react'
import type { NewsArticleRecord, NewsArticlesResponse } from '../types'

const POLL_MS = 5_000

export function useNewsArticles(opts?: {
  source?: string
  q?: string
  limit?: number
  offset?: number
}) {
  const source = opts?.source ?? 'all'
  const q = opts?.q ?? ''
  const limit = opts?.limit ?? 30
  const offset = opts?.offset ?? 0
  const [items, setItems] = useState<NewsArticleRecord[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const params = new URLSearchParams({
          source,
          limit: String(limit),
          offset: String(offset),
        })
        if (q.trim()) params.set('q', q.trim())
        const res = await fetch(`/api/news-articles?${params}`)
        if (!res.ok) throw new Error(`news-articles ${res.status}`)
        const data = (await res.json()) as NewsArticlesResponse
        if (!cancelled) {
          setItems(data.items ?? [])
          setTotal(data.total ?? 0)
          setFetchError(null)
          setLoading(false)
        }
      } catch (err) {
        if (!cancelled) {
          setFetchError(err instanceof Error ? err.message : 'offline')
          setLoading(false)
        }
      }
    }

    void load()
    const id = window.setInterval(() => void load(), POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [source, q, limit, offset])

  return { items, total, loading, fetchError }
}
