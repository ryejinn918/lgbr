import { isFnguideCrawlMode } from './collectNav'
import {
  DASHBOARD_COLLECT_JOBS,
  startArgsForJob,
  type DashboardCollectJobDef,
} from './dashboardCollectJobs'

const POLL_MS = 2_000
const WAIT_TIMEOUT_MS = 6 * 60 * 60 * 1000

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function isBusyState(state: string | null | undefined) {
  return state === 'starting' || state === 'active' || state === 'stopping'
}

function jobByKey(key: string): DashboardCollectJobDef {
  const def = DASHBOARD_COLLECT_JOBS.find((j) => j.key === key)
  if (!def) throw new Error(`unknown collect job: ${key}`)
  return def
}

async function readJson(res: Response) {
  return (await res.json()) as Record<string, unknown> & {
    ok?: boolean
    message?: string
    state?: string
    can_start?: boolean
    crawl?: { mode?: string | null; state?: string } | null
    job?: { state?: string } | null
  }
}

export async function isDashboardJobBusy(key: string): Promise<boolean> {
  const def = jobByKey(key)
  if (def.kind === 'fnguide_all_profiles') {
    const res = await fetch('/api/crawl?source=fnguide&events=0')
    if (!res.ok) throw new Error(`crawl status ${res.status}`)
    const data = await readJson(res)
    const mode = data.crawl?.mode ?? null
    return isBusyState(data.state) && isFnguideCrawlMode(mode)
  }
  const capability = def.capability ?? 'search'
  const params = new URLSearchParams({
    source: def.source,
    capability,
  })
  const res = await fetch(`/api/collection?${params}`)
  if (!res.ok) throw new Error(`collection status ${res.status}`)
  const data = await readJson(res)
  return isBusyState(data.state)
}

export async function canStartDashboardJob(key: string): Promise<{
  ok: boolean
  reason?: string
}> {
  const def = jobByKey(key)
  if (def.kind === 'fnguide_all_profiles') {
    const res = await fetch('/api/crawl?source=fnguide&events=0')
    if (!res.ok) return { ok: false, reason: `API ${res.status}` }
    const data = await readJson(res)
    if (data.can_start === true) return { ok: true }
    if (isBusyState(data.state)) return { ok: false, reason: '이미 실행 중' }
    return { ok: false, reason: data.message || '시작 불가' }
  }
  const capability = def.capability ?? 'search'
  const params = new URLSearchParams({
    source: def.source,
    capability,
  })
  const res = await fetch(`/api/collection?${params}`)
  if (!res.ok) return { ok: false, reason: `API ${res.status}` }
  const data = await readJson(res)
  if (data.can_start === true) return { ok: true }
  if (isBusyState(data.state)) return { ok: false, reason: '이미 실행 중' }
  return { ok: false, reason: data.message || '시작 불가' }
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

export async function waitUntilDashboardJobIdle(key: string): Promise<void> {
  const started = Date.now()
  // First poll after a short delay so "starting" is visible.
  await sleep(500)
  while (Date.now() - started < WAIT_TIMEOUT_MS) {
    if (!(await isDashboardJobBusy(key))) return
    await sleep(POLL_MS)
  }
  throw new Error(`${key} 대기 시간 초과`)
}

export type QueueResult = {
  started: string[]
  skipped: { key: string; reason: string }[]
  failed: { key: string; reason: string }[]
}

/** Sequential start; waits for each job to finish before the next. */
export async function runDashboardStartQueue(
  keys: string[],
  opts?: { onProgress?: (key: string, phase: 'start' | 'wait' | 'skip' | 'fail') => void },
): Promise<QueueResult> {
  const result: QueueResult = { started: [], skipped: [], failed: [] }
  for (const key of keys) {
    const gate = await canStartDashboardJob(key)
    if (!gate.ok) {
      opts?.onProgress?.(key, 'skip')
      result.skipped.push({ key, reason: gate.reason || '시작 불가' })
      continue
    }
    try {
      opts?.onProgress?.(key, 'start')
      await startDashboardJob(key)
      result.started.push(key)
      opts?.onProgress?.(key, 'wait')
      await waitUntilDashboardJobIdle(key)
    } catch (err) {
      opts?.onProgress?.(key, 'fail')
      result.failed.push({
        key,
        reason: err instanceof Error ? err.message : '실패',
      })
    }
  }
  return result
}
