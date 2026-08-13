import {
  DASHBOARD_COLLECT_JOBS,
  startArgsForJob,
  type DashboardCollectJobDef,
} from './dashboardCollectJobs'

function jobByKey(key: string): DashboardCollectJobDef {
  const def = DASHBOARD_COLLECT_JOBS.find((j) => j.key === key)
  if (!def) throw new Error(`unknown collect job: ${key}`)
  return def
}

async function readJson(res: Response) {
  return (await res.json()) as Record<string, unknown> & {
    ok?: boolean
    message?: string
  }
}

export async function startDashboardJob(key: string): Promise<void> {
  const def = jobByKey(key)
  const args = startArgsForJob(key)

  if (def.kind === 'fnguide_all_profiles') {
    const res = await fetch('/api/crawl/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: 'all_profiles' }),
    })
    const data = await readJson(res)
    if (!res.ok || data.ok === false) {
      throw new Error(data.message || `시작 실패 (${res.status})`)
    }
    return
  }

  const body: Record<string, unknown> = {
    source: def.source,
    capability: def.capability,
  }
  if (def.kind === 'collection_search') {
    body.max_pages = args.maxPages ?? 20
    if (args.periodMonths != null) body.period_months = args.periodMonths
    if (args.limit != null) body.limit = args.limit
    if (args.catalog) body.catalog = args.catalog
    if (args.profile) body.profile = args.profile
    if (args.itemDelaySeconds != null) {
      body.item_delay_seconds = args.itemDelaySeconds
    }
  } else if (def.kind === 'collection_feed') {
    body.max_pages = args.maxPages ?? 50
    body.period_months = args.periodMonths ?? 3
    if (args.section) body.section = args.section
  } else if (def.kind === 'collection_fetch_body') {
    body.limit = args.limit ?? 50
    body.delay_seconds = args.delaySeconds ?? 1.5
  }

  const res = await fetch('/api/collection/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await readJson(res)
  if (!res.ok || data.ok === false) {
    throw new Error(data.message || `시작 실패 (${res.status})`)
  }
}

export async function stopDashboardJob(key: string): Promise<void> {
  const def = jobByKey(key)
  if (def.kind === 'fnguide_all_profiles') {
    const res = await fetch('/api/crawl/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: 'fnguide' }),
    })
    const data = await readJson(res)
    if (!res.ok || data.ok === false) {
      throw new Error(data.message || `중단 실패 (${res.status})`)
    }
    return
  }
  const res = await fetch('/api/collection/stop', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source: def.source,
      capability: def.capability,
    }),
  })
  const data = await readJson(res)
  if (!res.ok || data.ok === false) {
    throw new Error(data.message || `중단 실패 (${res.status})`)
  }
}
