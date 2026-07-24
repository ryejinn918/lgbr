import { useCallback, useEffect, useState } from 'react'
import type {
  ConsensusRun,
  ConsensusStatusResponse,
  ConsensusTheme,
} from '../types'

const POLL_MS = 3_000

const EMPTY: ConsensusStatusResponse = {
  ok: true,
  label: '대기',
  state: 'idle',
  run: null,
  progress: {},
  events: [],
  can_start: true,
}

export function useConsensusStatus(theme?: ConsensusTheme) {
  const [status, setStatus] = useState<ConsensusStatusResponse>(EMPTY)
  const [history, setHistory] = useState<ConsensusRun[]>([])
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [requestingStart, setRequestingStart] = useState(false)
  const [requestingStop, setRequestingStop] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const histQs = new URLSearchParams({ limit: '2' })
      if (theme) histQs.set('theme', theme)
      const [cur, hist] = await Promise.all([
        fetch('/api/consensus?events=50').then((r) => r.json()),
        fetch(`/api/consensus/history?${histQs}`).then((r) => r.json()),
      ])
      setStatus({
        ok: !!cur.ok,
        label: cur.label ?? '대기',
        state: cur.state ?? 'idle',
        run: cur.run ?? null,
        progress: cur.progress ?? {},
        events: cur.events ?? [],
        can_start: cur.can_start ?? true,
        message: cur.message,
      })
      setHistory(hist.items ?? [])
      setFetchError(null)
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : 'fetch failed')
    }
  }, [theme])

  useEffect(() => {
    void refresh()
    const t = window.setInterval(() => void refresh(), POLL_MS)
    return () => window.clearInterval(t)
  }, [refresh])

  const startRun = useCallback(
    async (runTheme: ConsensusTheme) => {
      setRequestingStart(true)
      try {
        const res = await fetch('/api/consensus/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ theme: runTheme }),
        })
        const data = await res.json()
        if (!res.ok || !data.ok) {
          throw new Error(data.message || `HTTP ${res.status}`)
        }
        await refresh()
      } finally {
        setRequestingStart(false)
      }
    },
    [refresh],
  )

  const stopRun = useCallback(async () => {
    setRequestingStop(true)
    try {
      const res = await fetch('/api/consensus/stop', { method: 'POST' })
      const data = await res.json()
      if (!res.ok || !data.ok) {
        throw new Error(data.message || `HTTP ${res.status}`)
      }
      await refresh()
    } finally {
      setRequestingStop(false)
    }
  }, [refresh])

  return {
    status,
    history,
    fetchError,
    requestingStart,
    requestingStop,
    refresh,
    startRun,
    stopRun,
  }
}
