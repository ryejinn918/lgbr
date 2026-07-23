import { useCallback, useEffect, useState } from 'react'
import type { AuditJob, AuditResponse, AuditState } from '../types'

const POLL_MS = 3_000

export type AuditView = {
  state: AuditState
  label: string
  message: string | null
  audit: AuditJob | null
  canStart: boolean
  busy: boolean
  error: string | null
  starting: boolean
  refresh: () => Promise<void>
  startPending: (opts?: {
    theme?: string
    limit?: number
  }) => Promise<boolean>
  startOne: (reportId: string) => Promise<boolean>
}

export function useAudit(): AuditView {
  const [state, setState] = useState<AuditState>('idle')
  const [label, setLabel] = useState('대기')
  const [message, setMessage] = useState<string | null>(null)
  const [audit, setAudit] = useState<AuditJob | null>(null)
  const [canStart, setCanStart] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const res = await fetch('/api/audit')
      const data = (await res.json()) as AuditResponse
      if (!res.ok) {
        throw new Error(data.message || `HTTP ${res.status}`)
      }
      setState(data.state || 'idle')
      setLabel(data.label || data.audit?.label || '대기')
      setMessage(data.message ?? data.audit?.message ?? null)
      setAudit(data.audit ?? null)
      setCanStart(data.can_start !== false)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'fetch failed')
    }
  }, [])

  useEffect(() => {
    void refresh()
    const id = window.setInterval(() => {
      void refresh()
    }, POLL_MS)
    return () => window.clearInterval(id)
  }, [refresh])

  const start = useCallback(
    async (body: Record<string, unknown>): Promise<boolean> => {
      setStarting(true)
      try {
        const res = await fetch('/api/audit/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
        const data = (await res.json()) as AuditResponse
        if (!res.ok) {
          throw new Error(data.message || `HTTP ${res.status}`)
        }
        setState(data.state || 'starting')
        setLabel(data.label || '시작 중')
        setMessage(data.message ?? null)
        setAudit(data.audit ?? null)
        setCanStart(false)
        setError(null)
        await refresh()
        return true
      } catch (err) {
        setError(err instanceof Error ? err.message : 'start failed')
        return false
      } finally {
        setStarting(false)
      }
    },
    [refresh],
  )

  const startPending = useCallback(
    async (opts?: { theme?: string; limit?: number }) => {
      const body: Record<string, unknown> = { force: false }
      if (opts?.theme && opts.theme !== 'all') body.theme = opts.theme
      if (opts?.limit != null) body.limit = opts.limit
      return start(body)
    },
    [start],
  )

  const startOne = useCallback(
    async (reportId: string) => {
      return start({ report_id: reportId, force: true })
    },
    [start],
  )

  const busy = state === 'starting' || state === 'active' || starting

  return {
    state,
    label,
    message,
    audit,
    canStart: canStart && !busy,
    busy,
    error,
    starting,
    refresh,
    startPending,
    startOne,
  }
}
