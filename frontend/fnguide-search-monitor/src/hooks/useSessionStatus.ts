import { useEffect, useState } from 'react'
import type { HistoryResponse, SessionResponse } from '../types'

const STALE_AFTER_MS = 30_000
const POLL_MS = 2_000

const EMPTY: SessionResponse = {
  state: 'ended',
  label: '로그아웃됨',
  session: null,
}

export type SessionView = {
  status: SessionResponse
  history: HistoryResponse['items']
  stale: boolean
  fetchError: string | null
  requestingLogout: boolean
  requestLogout: () => Promise<void>
}

function isStale(status: SessionResponse, now: number): boolean {
  // Idle 유지 중에는 last_used_at이 안 바뀌는 것이 정상.
  // 로그인/로그아웃 전환이 멈춘 경우만 응답 없음으로 본다.
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

export function useSessionStatus(): SessionView {
  const [status, setStatus] = useState<SessionResponse>(EMPTY)
  const [history, setHistory] = useState<HistoryResponse['items']>([])
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [requestingLogout, setRequestingLogout] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const [sessionRes, historyRes] = await Promise.all([
          fetch('/api/session'),
          fetch('/api/session/history?limit=30'),
        ])
        if (!sessionRes.ok) throw new Error(`HTTP ${sessionRes.status}`)
        if (!historyRes.ok) throw new Error(`HTTP ${historyRes.status}`)
        const sessionData = (await sessionRes.json()) as SessionResponse
        const historyData = (await historyRes.json()) as HistoryResponse
        if (cancelled) return
        setStatus(sessionData)
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

  async function requestLogout() {
    setRequestingLogout(true)
    try {
      const res = await fetch('/api/session/logout', { method: 'POST' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = (await res.json()) as {
        session: SessionResponse['session']
        label?: string
      }
      if (data.session) {
        setStatus({
          state: data.session.state,
          label: data.session.label,
          session: data.session,
        })
      }
    } finally {
      setRequestingLogout(false)
    }
  }

  return {
    status,
    history,
    stale: isStale(status, now),
    fetchError,
    requestingLogout,
    requestLogout,
  }
}
