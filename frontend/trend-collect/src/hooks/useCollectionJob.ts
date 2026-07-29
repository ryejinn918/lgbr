import { useEffect, useState } from 'react'
import type {
  CollectionCapability,
  CollectionJobResponse,
} from '../types'

const POLL_MS = 2_000

const EMPTY: CollectionJobResponse = {
  state: 'ended',
  label: '종료',
  job: null,
  progress: {},
  can_start: true,
}

export function useCollectionJob(opts?: {
  source?: string
  capability?: CollectionCapability
}) {
  const source = opts?.source ?? 'arg'
  const capability = opts?.capability ?? 'feed'
  const [status, setStatus] = useState<CollectionJobResponse>(EMPTY)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [requestingStart, setRequestingStart] = useState(false)
  const [requestingStop, setRequestingStop] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const params = new URLSearchParams({
          source,
          capability,
        })
        const res = await fetch(`/api/collection?${params}`)
        if (!res.ok) {
          throw new Error(`collection ${res.status}`)
        }
        const data = (await res.json()) as CollectionJobResponse
        if (!cancelled) {
          setStatus({
            state: data.state ?? 'ended',
            label: data.label ?? '종료',
            job: data.job ?? null,
            progress: data.progress ?? data.job?.progress ?? {},
            can_start: data.can_start ?? false,
          })
          setFetchError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setFetchError(err instanceof Error ? err.message : 'offline')
        }
      }
    }

    void poll()
    const id = window.setInterval(() => void poll(), POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [source, capability])

  async function startFeed(opts?: {
    maxPages?: number
    periodMonths?: number
  }) {
    const maxPages = opts?.maxPages ?? 50
    const periodMonths = opts?.periodMonths ?? 3
    setRequestingStart(true)
    try {
      const res = await fetch('/api/collection/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source,
          capability: 'feed',
          max_pages: maxPages,
          period_months: periodMonths,
        }),
      })
      const data = (await res.json()) as CollectionJobResponse & {
        ok?: boolean
        message?: string
      }
      if (!res.ok || data.ok === false) {
        throw new Error(data.message || `start failed (${res.status})`)
      }
      setStatus({
        state: data.state ?? data.job?.state ?? 'starting',
        label: data.label ?? data.job?.label ?? '시작 중',
        job: data.job ?? null,
        progress: data.progress ?? data.job?.progress ?? {},
        can_start: false,
      })
    } finally {
      setRequestingStart(false)
    }
  }

  async function startSearch(opts?: {
    maxPages?: number
    periodMonths?: number
    limit?: number
  }) {
    const maxPages = opts?.maxPages ?? 20
    const periodMonths = opts?.periodMonths ?? 3
    setRequestingStart(true)
    try {
      const body: Record<string, unknown> = {
        source,
        capability: 'search',
        max_pages: maxPages,
        period_months: periodMonths,
      }
      if (opts?.limit != null) body.limit = opts.limit
      const res = await fetch('/api/collection/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = (await res.json()) as CollectionJobResponse & {
        ok?: boolean
        message?: string
      }
      if (!res.ok || data.ok === false) {
        throw new Error(data.message || `start failed (${res.status})`)
      }
      setStatus({
        state: data.state ?? data.job?.state ?? 'starting',
        label: data.label ?? data.job?.label ?? '시작 중',
        job: data.job ?? null,
        progress: data.progress ?? data.job?.progress ?? {},
        can_start: false,
      })
    } finally {
      setRequestingStart(false)
    }
  }

  async function startFetchBody(opts?: {
    limit?: number
    delaySeconds?: number
  }) {
    const limit = opts?.limit ?? 200
    const delaySeconds = opts?.delaySeconds ?? 1
    setRequestingStart(true)
    try {
      const res = await fetch('/api/collection/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source,
          capability: 'fetch_body',
          limit,
          delay_seconds: delaySeconds,
        }),
      })
      const data = (await res.json()) as CollectionJobResponse & {
        ok?: boolean
        message?: string
      }
      if (!res.ok || data.ok === false) {
        throw new Error(data.message || `start failed (${res.status})`)
      }
      setStatus({
        state: data.state ?? data.job?.state ?? 'starting',
        label: data.label ?? data.job?.label ?? '시작 중',
        job: data.job ?? null,
        progress: data.progress ?? data.job?.progress ?? {},
        can_start: false,
      })
    } finally {
      setRequestingStart(false)
    }
  }

  async function stopFeed() {
    setRequestingStop(true)
    try {
      const res = await fetch('/api/collection/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source, capability }),
      })
      const data = (await res.json()) as CollectionJobResponse & {
        ok?: boolean
        message?: string
      }
      if (!res.ok || data.ok === false) {
        throw new Error(data.message || `stop failed (${res.status})`)
      }
      if (data.job) {
        setStatus({
          state: data.state ?? data.job.state,
          label: data.label ?? data.job.label,
          job: data.job,
          progress: data.progress ?? data.job.progress ?? {},
          can_start: false,
        })
      }
    } finally {
      setRequestingStop(false)
    }
  }

  return {
    status,
    fetchError,
    requestingStart,
    requestingStop,
    startFeed,
    startSearch,
    startFetchBody,
    stopFeed,
  }
}
