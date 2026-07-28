import { useCallback, useEffect, useRef, useState } from 'react'
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

export type ContinuePayload = {
  thesis?: string
  cut_logic?: string
  pillar_sketch?: string[]
  until?: 'select'
  resume_from?: 'select' | 'doc'
}

export function useConsensusStatus(theme?: ConsensusTheme) {
  const [status, setStatus] = useState<ConsensusStatusResponse>(EMPTY)
  const [history, setHistory] = useState<ConsensusRun[]>([])
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [requestingStart, setRequestingStart] = useState(false)
  const [requestingStop, setRequestingStop] = useState(false)
  const themeRef = useRef(theme)
  const genRef = useRef(0)
  themeRef.current = theme

  const refresh = useCallback(async () => {
    const requestedTheme = themeRef.current
    const gen = genRef.current
    try {
      const histQs = new URLSearchParams({ limit: '2' })
      if (requestedTheme) histQs.set('theme', requestedTheme)
      const [cur, hist] = await Promise.all([
        fetch('/api/consensus?events=50').then((r) => r.json()),
        fetch(`/api/consensus/history?${histQs}`).then((r) => r.json()),
      ])
      if (genRef.current !== gen || themeRef.current !== requestedTheme) return
      setStatus(() => ({
        ok: !!cur.ok,
        label: cur.label ?? '대기',
        state: cur.state ?? 'idle',
        run: cur.run ?? null,
        progress: cur.progress ?? {},
        events: cur.events ?? [],
        can_start: cur.can_start ?? true,
        message: cur.message,
      }))
      setHistory(() => hist.items ?? [])
      setFetchError(() => null)
    } catch (e) {
      if (genRef.current !== gen || themeRef.current !== requestedTheme) return
      setFetchError(() => (e instanceof Error ? e.message : 'fetch failed'))
    }
  }, [])

  useEffect(() => {
    genRef.current += 1
    setHistory(() => [])
    setStatus(() => EMPTY)
    setFetchError(() => null)
    void refresh()
    const t = window.setInterval(() => void refresh(), POLL_MS)
    return () => {
      genRef.current += 1
      window.clearInterval(t)
    }
  }, [theme, refresh])

  const startRun = useCallback(
    async (runTheme: ConsensusTheme) => {
      setRequestingStart(() => true)
      try {
        const res = await fetch('/api/consensus/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ theme: runTheme, until: 'thesis' }),
        })
        const data = await res.json()
        if (!res.ok || !data.ok) {
          throw new Error(data.message || `HTTP ${res.status}`)
        }
        await refresh()
      } finally {
        setRequestingStart(() => false)
      }
    },
    [refresh],
  )

  const continueRun = useCallback(
    async (runId: string, payload: ContinuePayload) => {
      const res = await fetch(`/api/consensus/runs/${runId}/continue`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (!res.ok || !data.ok) {
        throw new Error(data.message || `HTTP ${res.status}`)
      }
      await refresh()
    },
    [refresh],
  )

  const stopRun = useCallback(async () => {
    setRequestingStop(() => true)
    try {
      const res = await fetch('/api/consensus/stop', { method: 'POST' })
      const data = await res.json()
      if (!res.ok || !data.ok) {
        throw new Error(data.message || `HTTP ${res.status}`)
      }
      await refresh()
    } finally {
      setRequestingStop(() => false)
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
    continueRun,
    stopRun,
  }
}
