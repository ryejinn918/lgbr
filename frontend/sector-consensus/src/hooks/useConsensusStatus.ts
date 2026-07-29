import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  ConsensusRun,
  ConsensusStatusResponse,
  ConsensusTheme,
} from '../types'

const POLL_MS = 3_000
const SNAPSHOT_PREFIX = 'lgbr:consensus:status:'

const EMPTY: ConsensusStatusResponse = {
  ok: true,
  label: '대기',
  state: 'idle',
  run: null,
  progress: {},
  events: [],
  can_start: true,
}

type ConnectionState = 'loading' | 'online' | 'offline'

type StatusSnapshot = {
  status: ConsensusStatusResponse
  history: ConsensusRun[]
  savedAt: string
}

function snapshotKey(theme?: ConsensusTheme): string {
  return `${SNAPSHOT_PREFIX}${theme ?? 'global'}`
}

function readSnapshot(theme?: ConsensusTheme): StatusSnapshot | null {
  try {
    const raw = window.sessionStorage.getItem(snapshotKey(theme))
    if (!raw) return null
    const value = JSON.parse(raw) as Partial<StatusSnapshot>
    if (
      !value.status ||
      typeof value.status !== 'object' ||
      !Array.isArray(value.history) ||
      typeof value.savedAt !== 'string'
    ) {
      return null
    }
    return value as StatusSnapshot
  } catch {
    return null
  }
}

function writeSnapshot(
  theme: ConsensusTheme | undefined,
  status: ConsensusStatusResponse,
  history: ConsensusRun[],
): void {
  try {
    window.sessionStorage.setItem(
      snapshotKey(theme),
      JSON.stringify({ status, history, savedAt: new Date().toISOString() }),
    )
  } catch {
    // Polling remains authoritative when session storage is unavailable.
  }
}

async function fetchJson(url: string): Promise<Record<string, any>> {
  const response = await fetch(url)
  const data = await response.json()
  if (!response.ok || !data.ok) {
    throw new Error(data.message || `HTTP ${response.status}`)
  }
  return data
}

export type ContinuePayload = {
  thesis?: string
  cut_logic?: string
  pillar_sketch?: string[]
  until?: 'select'
  resume_from?: 'select' | 'doc'
}

export function useConsensusStatus(theme?: ConsensusTheme) {
  const initialSnapshot = readSnapshot(theme)
  const [status, setStatus] = useState<ConsensusStatusResponse>(
    initialSnapshot?.status ?? EMPTY,
  )
  const [history, setHistory] = useState<ConsensusRun[]>(
    initialSnapshot?.history ?? [],
  )
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [connectionState, setConnectionState] =
    useState<ConnectionState>('loading')
  const [hasSnapshot, setHasSnapshot] = useState(initialSnapshot !== null)
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
        fetchJson('/api/consensus?events=50'),
        fetchJson(`/api/consensus/history?${histQs}`),
      ])
      if (genRef.current !== gen || themeRef.current !== requestedTheme) return
      const nextStatus: ConsensusStatusResponse = {
        ok: !!cur.ok,
        label: cur.label ?? '대기',
        state: cur.state ?? 'idle',
        run: cur.run ?? null,
        progress: cur.progress ?? {},
        events: cur.events ?? [],
        can_start: cur.can_start ?? true,
        message: cur.message,
      }
      const nextHistory = (hist.items ?? []) as ConsensusRun[]
      setStatus(() => nextStatus)
      setHistory(() => nextHistory)
      setFetchError(() => null)
      setConnectionState(() => 'online')
      setHasSnapshot(() => true)
      writeSnapshot(requestedTheme, nextStatus, nextHistory)
    } catch (e) {
      if (genRef.current !== gen || themeRef.current !== requestedTheme) return
      setFetchError(() => (e instanceof Error ? e.message : 'fetch failed'))
      setConnectionState(() => 'offline')
    }
  }, [])

  useEffect(() => {
    genRef.current += 1
    const cached = readSnapshot(theme)
    setHistory(() => cached?.history ?? [])
    setStatus(() => cached?.status ?? EMPTY)
    setHasSnapshot(() => cached !== null)
    setConnectionState(() => 'loading')
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
    connectionState,
    hasSnapshot,
    requestingStart,
    requestingStop,
    refresh,
    startRun,
    continueRun,
    stopRun,
  }
}
