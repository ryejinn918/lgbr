import { useEffect, useState } from 'react'
import type { CrawlRecord } from '../types'

const POLL_MS = 15_000

type HistoryLatestResponse = {
  ok?: boolean
  crawl?: CrawlRecord | null
  message?: string
}

export type FnguideLatestView = {
  crawl: CrawlRecord | null
  error: string | null
}

export function useFnguideLatestCrawl(): FnguideLatestView {
  const [crawl, setCrawl] = useState<CrawlRecord | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const res = await fetch('/api/crawl/history-latest?family=fnguide')
        const data = (await res.json()) as HistoryLatestResponse
        if (!res.ok) {
          throw new Error(data.message || `HTTP ${res.status}`)
        }
        if (cancelled) return
        setCrawl(data.crawl ?? null)
        setError(null)
      } catch (err) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : 'fetch failed')
      }
    }

    void poll()
    const id = window.setInterval(() => {
      void poll()
    }, POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  return { crawl, error }
}
