import { useEffect, useState } from 'react'
import type { SessionStatus } from '../types'

const STALE_AFTER_MS = 30_000
const POLL_MS = 2_000

const IDLE: SessionStatus = {
  state: 'idle',
  user_id: null,
  started_at: null,
  updated_at: null,
  pid: null,
  current_url: null,
  step: null,
  message: null,
}

export type SessionView = {
  status: SessionStatus
  stale: boolean
  fetchError: string | null
  lastFetchedAt: number | null
}

function isStale(status: SessionStatus, now: number): boolean {
  if (status.state === 'idle' || !status.updated_at) return false
  const updated = Date.parse(status.updated_at)
  if (Number.isNaN(updated)) return true
  return now - updated > STALE_AFTER_MS
}

export function useSessionStatus(): SessionView {
  const [status, setStatus] = useState<SessionStatus>(IDLE)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [lastFetchedAt, setLastFetchedAt] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const res = await fetch('/api/session')
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = (await res.json()) as SessionStatus
        if (cancelled) return
        setStatus(data)
        setFetchError(null)
        setLastFetchedAt(Date.now())
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

  return {
    status,
    stale: isStale(status, now),
    fetchError,
    lastFetchedAt,
  }
}
