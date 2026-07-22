import { useCallback, useEffect, useState } from 'react'
import type { CrawlProfile, CrawlProfileMode } from '../types'

type ProfilesState = {
  items: CrawlProfile[]
  loading: boolean
  error: string | null
  saving: CrawlProfileMode | null
  refresh: () => Promise<void>
  saveProfile: (
    mode: CrawlProfileMode,
    patch: Partial<
      Pick<
        CrawlProfile,
        'keyword' | 'sectors' | 'period_months' | 'page_min_label'
      >
    >,
  ) => Promise<CrawlProfile>
}

const EMPTY: CrawlProfile[] = []

export function useCrawlProfiles(): ProfilesState {
  const [items, setItems] = useState<CrawlProfile[]>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState<CrawlProfileMode | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/crawl/profiles')
      const data = (await res.json()) as {
        ok?: boolean
        items?: CrawlProfile[]
        message?: string
      }
      if (!res.ok || data.ok === false) {
        throw new Error(data.message || `HTTP ${res.status}`)
      }
      setItems(data.items ?? [])
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'fetch failed')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const saveProfile = useCallback(
    async (
      mode: CrawlProfileMode,
      patch: Partial<
        Pick<
          CrawlProfile,
          'keyword' | 'sectors' | 'period_months' | 'page_min_label'
        >
      >,
    ) => {
      setSaving(mode)
      try {
        const res = await fetch(`/api/crawl/profiles/${mode}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(patch),
        })
        const data = (await res.json()) as {
          ok?: boolean
          profile?: CrawlProfile
          message?: string
        }
        if (!res.ok || data.ok === false || !data.profile) {
          throw new Error(data.message || `HTTP ${res.status}`)
        }
        setItems((prev) =>
          prev.map((p) => (p.mode === mode ? data.profile! : p)),
        )
        setError(null)
        return data.profile
      } finally {
        setSaving(null)
      }
    },
    [],
  )

  return { items, loading, error, saving, refresh, saveProfile }
}
