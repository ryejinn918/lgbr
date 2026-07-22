import { useEffect, useState } from 'react'
import type {
  CrawlMode,
  CrawlResponse,
  HistoryResponse,
  SessionResponse,
} from '../types'

const STALE_AFTER_MS = 30_000
const POLL_MS = 2_000

const EMPTY_SESSION: SessionResponse = {
  state: 'ended',
  label: '로그아웃됨',
  session: null,
}

const EMPTY_CRAWL: CrawlResponse = {
  state: 'ended',
  label: '종료',
  crawl: null,
  progress: {},
  events: [],
  session: EMPTY_SESSION,
  can_start: true,
}

export type SessionView = {
  crawl: CrawlResponse
  status: SessionResponse
  history: HistoryResponse['items']
  stale: boolean
  fetchError: string | null
  requestingStart: boolean
  requestingStop: boolean
  startCrawl: (
    mode?: CrawlMode,
    limit?: number,
    opts?: { debug?: boolean },
  ) => Promise<void>
  requestLogout: () => Promise<void>
}

function isStale(status: SessionResponse, now: number): boolean {
  if (
    !status.session ||
    (status.state !== 'logging_in' && status.state !== 'logging_out')
  ) {
    return false
  }
  const updated = status.session.last_used_at || status.session.started_at
  if (!updated) return false
  const ms = Date.parse(updated)
  if (Number.isNaN(ms)) return true
  return now - ms > STALE_AFTER_MS
}

function applyCrawl(data: CrawlResponse): CrawlResponse {
  return {
    state: data.state,
    label: data.label,
    crawl: data.crawl ?? null,
    progress: data.progress ?? data.crawl?.progress ?? {},
    events: data.events ?? [],
    session: data.session ?? EMPTY_SESSION,
    can_start: data.can_start ?? false,
    unblock_sql: data.unblock_sql ?? null,
    db: data.db ?? null,
    unblock_text: data.unblock_text ?? null,
  }
}

export function useSessionStatus(): SessionView {
  const [crawl, setCrawl] = useState<CrawlResponse>(EMPTY_CRAWL)
  const [status, setStatus] = useState<SessionResponse>(EMPTY_SESSION)
  const [history, setHistory] = useState<HistoryResponse['items']>([])
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [requestingStart, setRequestingStart] = useState(false)
  const [requestingStop, setRequestingStop] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const [crawlRes, historyRes] = await Promise.all([
          fetch('/api/crawl'),
          fetch('/api/session/history?limit=30'),
        ])
        if (!crawlRes.ok) throw new Error(`HTTP ${crawlRes.status}`)
        if (!historyRes.ok) throw new Error(`HTTP ${historyRes.status}`)
        const crawlData = (await crawlRes.json()) as CrawlResponse
        const historyData = (await historyRes.json()) as HistoryResponse
        if (cancelled) return
        setCrawl(applyCrawl(crawlData))
        setStatus(crawlData.session ?? EMPTY_SESSION)
        setHistory(historyData.items ?? [])
        setFetchError(null)
        setNow(Date.now())
      } catch (err) {
        if (cancelled) return
        setFetchError(err instanceof Error ? err.message : 'fetch failed')
        setNow(Date.now())
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

  async function startCrawl(
    mode: CrawlMode = 'datacenter',
    limit = 5,
    opts?: { debug?: boolean },
  ) {
    setRequestingStart(true)
    try {
      const body: { mode: CrawlMode; limit?: number; debug?: boolean } = { mode }
      if (mode === 'datacenter') {
        body.limit = limit
        if (opts?.debug) body.debug = true
      }
      const res = await fetch('/api/crawl/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = (await res.json()) as CrawlResponse & {
        ok?: boolean
        message?: string
      }
      if (!res.ok) {
        throw new Error(data.message || `HTTP ${res.status}`)
      }
      setCrawl(applyCrawl(data))
      if (data.session) setStatus(data.session)
    } finally {
      setRequestingStart(false)
    }
  }

  async function requestLogout() {
    setRequestingStop(true)
    try {
      const res = await fetch('/api/crawl/stop', { method: 'POST' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = (await res.json()) as CrawlResponse
      setCrawl(applyCrawl(data))
      if (data.session) setStatus(data.session)
    } finally {
      setRequestingStop(false)
    }
  }

  return {
    crawl,
    status,
    history,
    stale: isStale(status, now),
    fetchError,
    requestingStart,
    requestingStop,
    startCrawl,
    requestLogout,
  }
}
