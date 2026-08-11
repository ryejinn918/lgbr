import { useEffect, useState } from 'react'
import { isSearchProfileMode } from '../lib/themes'
import type { CrawlMode, CrawlResponse, SessionResponse } from '../types'

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
  stale: boolean
  fetchError: string | null
  requestingStart: boolean
  requestingStop: boolean
  requestingClearError: boolean
  startCrawl: (
    mode?: CrawlMode,
    opts?: { debug?: boolean; catalog?: string },
  ) => Promise<void>
  requestLogout: () => Promise<void>
  clearError: () => Promise<void>
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

export function useSessionStatus(opts?: { source?: string }): SessionView {
  const source = (opts?.source || 'fnguide').trim() || 'fnguide'
  const [crawl, setCrawl] = useState<CrawlResponse>(EMPTY_CRAWL)
  const [status, setStatus] = useState<SessionResponse>(EMPTY_SESSION)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [requestingStart, setRequestingStart] = useState(false)
  const [requestingStop, setRequestingStop] = useState(false)
  const [requestingClearError, setRequestingClearError] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const qs = new URLSearchParams({ source })
        const crawlRes = await fetch(`/api/crawl?${qs.toString()}`)
        if (!crawlRes.ok) throw new Error(`HTTP ${crawlRes.status}`)
        const crawlData = (await crawlRes.json()) as CrawlResponse
        if (cancelled) return
        setCrawl(applyCrawl(crawlData))
        setStatus(crawlData.session ?? EMPTY_SESSION)
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
  }, [source])

  async function startCrawl(
    mode: CrawlMode = 'ai',
    opts?: { debug?: boolean; catalog?: string },
  ) {
    setRequestingStart(true)
    try {
      const body: { mode: CrawlMode; debug?: boolean; catalog?: string } = {
        mode,
      }
      if (isSearchProfileMode(mode) && opts?.debug) {
        body.debug = true
      }
      if (mode === 'pwc' && opts?.catalog) {
        body.catalog = opts.catalog
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
      const res = await fetch('/api/crawl/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = (await res.json()) as CrawlResponse
      setCrawl(applyCrawl(data))
      if (data.session) setStatus(data.session)
    } finally {
      setRequestingStop(false)
    }
  }

  async function clearError() {
    setRequestingClearError(true)
    try {
      const res = await fetch('/api/crawl/clear-error', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source }),
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
      setRequestingClearError(false)
    }
  }

  return {
    crawl,
    status,
    stale: isStale(status, now),
    fetchError,
    requestingStart,
    requestingStop,
    requestingClearError,
    startCrawl,
    requestLogout,
    clearError,
  }
}
