import { useCallback, useEffect, useState } from 'react'
import type { CoverageResponse, CoverageSourceRow } from '../types'

const POLL_MS = 60_000

export type CoverageView = {
  weeks: string[]
  sources: CoverageSourceRow[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useCoverage(weeks = 13): CoverageView {
  const [weekKeys, setWeekKeys] = useState<string[]>([])
  const [sources, setSources] = useState<CoverageSourceRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`/api/reports/coverage?weeks=${weeks}`)
      const data = (await res.json()) as CoverageResponse
      if (!res.ok) {
        throw new Error(data.message || `HTTP ${res.status}`)
      }
      setWeekKeys(data.weeks ?? [])
      setSources(data.sources ?? [])
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'fetch failed')
    } finally {
      setLoading(false)
    }
  }, [weeks])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void refresh().then(() => {
      if (cancelled) return
    })
    const id = window.setInterval(() => {
      void refresh()
    }, POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [refresh])

  return {
    weeks: weekKeys,
    sources,
    loading,
    error,
    refresh,
  }
}
