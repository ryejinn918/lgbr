import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CollectJobRow } from '../components/CollectJobRow'
import { CoverageGrass } from '../components/CoverageGrass'
import { useAudit } from '../hooks/useAudit'
import { useCollectionJob } from '../hooks/useCollectionJob'
import { useCoverage } from '../hooks/useCoverage'
import { useFnguideLatestCrawl } from '../hooks/useFnguideLatestCrawl'
import { useReports } from '../hooks/useReports'
import { useSessionStatus } from '../hooks/useSessionStatus'
import {
  serializeReportFilters,
  unauditedPreset,
} from '../lib/reportFilters'
import {
  runDashboardStartQueue,
  startDashboardJob,
  stopDashboardJob,
} from '../lib/dashboardCollectActions'
import {
  DASHBOARD_COLLECT_JOBS,
  startConfirmLabel,
  type DashboardCollectJobDef,
} from '../lib/dashboardCollectJobs'
import { crawlModeTypeLabel, isFnguideCrawlMode } from '../lib/collectNav'
import {
  CRAWL_CLASS,
  STATUS_LABEL,
  formatProgress,
  formatPublishedAt,
} from '../lib/format'
import type { CollectionJobRecord, CollectionJobResponse } from '../types'

const RECENT_WINDOW_MS = 12 * 60 * 60 * 1000
const RECENT_PAGE_SIZE = 15

const SOURCE_LABEL: Record<string, string> = {
  fnguide: 'FnGuide',
  pwc: 'PwC',
  accenture: 'Accenture',
  kpmg: 'KPMG',
  ey: 'EY',
  deloitte: 'Deloitte',
  hbr: 'HBR',
  hbrkorea: 'HBR Korea',
  mckinsey: 'McKinsey',
  bain: 'Bain',
  bcg: 'BCG',
  nikkei: 'Nikkei',
  nikkeixtech: 'Nikkei xTECH',
  arg: 'ARG',
}

function sourceLabel(source: string | null | undefined) {
  if (!source) return '—'
  return SOURCE_LABEL[source] ?? source
}

function isBusy(state: string) {
  return state === 'starting' || state === 'active' || state === 'stopping'
}

function jobTimestamp(
  job: { started_at?: string | null; ended_at?: string | null } | null | undefined,
): string | null {
  return job?.ended_at ?? job?.started_at ?? null
}

function formatSearchProgress(progress: Record<string, unknown> | undefined) {
  if (!progress) return null
  const bits: string[] = []
  if (progress.pages_done != null)
    bits.push(`목록 ${String(progress.pages_done)}`)
  if (progress.listed != null) bits.push(`목록항목 ${String(progress.listed)}`)
  if (progress.downloaded != null)
    bits.push(`수집 ${String(progress.downloaded)}`)
  if (progress.skipped_blind != null)
    bits.push(`본문제한 ${String(progress.skipped_blind)}`)
  if (progress.skipped_no_download != null)
    bits.push(`수집불가 ${String(progress.skipped_no_download)}`)
  if (progress.current_title)
    bits.push(String(progress.current_title).slice(0, 48))
  return bits.length ? bits.join(' · ') : null
}

function formatBodyProgress(progress: Record<string, unknown> | undefined) {
  if (!progress) return null
  const bits: string[] = []
  if (progress.done != null && progress.total != null) {
    bits.push(`${String(progress.done)}/${String(progress.total)}`)
  }
  if (progress.fetched != null) bits.push(`성공 ${String(progress.fetched)}`)
  if (progress.failed != null) bits.push(`실패 ${String(progress.failed)}`)
  return bits.length ? bits.join(' · ') : null
}

function jobBadgeClass(
  offline: boolean,
  busy: boolean,
  state: string,
): string {
  if (offline) return 'offline'
  if (busy) {
    return CRAWL_CLASS[state as keyof typeof CRAWL_CLASS] ?? 'active'
  }
  return 'ended'
}

function collectionStatusLabel(
  fetchError: string | null,
  busy: boolean,
  status: CollectionJobResponse,
): string {
  if (fetchError) return 'API Offline'
  if (busy) return status.label
  if (status.job) return status.label
  return '유휴'
}

type RowView = {
  def: DashboardCollectJobDef
  statusLabel: string
  stateClass: string
  lastCollectedAt: string | null
  lastDocAt: string | null
  progressLine: string | null
  busy: boolean
  canStart: boolean
  offline: boolean
}

export function DashboardPage() {
  const { crawl, status, stale, fetchError } = useSessionStatus({
    source: 'fnguide',
  })
  const fgLatest = useFnguideLatestCrawl()
  const argFeed = useCollectionJob({ source: 'arg', capability: 'feed' })
  const nikkeiFeed = useCollectionJob({ source: 'nikkei', capability: 'feed' })
  const nikkeiBody = useCollectionJob({
    source: 'nikkei',
    capability: 'fetch_body',
  })
  const pwcSearch = useCollectionJob({ source: 'pwc', capability: 'search' })
  const accentureSearch = useCollectionJob({
    source: 'accenture',
    capability: 'search',
  })
  const kpmgSearch = useCollectionJob({ source: 'kpmg', capability: 'search' })
  const eySearch = useCollectionJob({ source: 'ey', capability: 'search' })
  const deloitteSearch = useCollectionJob({
    source: 'deloitte',
    capability: 'search',
  })
  const hbrkoreaSearch = useCollectionJob({
    source: 'hbrkorea',
    capability: 'search',
  })
  const bainSearch = useCollectionJob({ source: 'bain', capability: 'search' })
  const bcgSearch = useCollectionJob({ source: 'bcg', capability: 'search' })
  const hbrSearch = useCollectionJob({ source: 'hbr', capability: 'search' })

  const collectionByKey: Record<
    string,
    ReturnType<typeof useCollectionJob>
  > = {
    'pwc:search': pwcSearch,
    'accenture:search': accentureSearch,
    'kpmg:search': kpmgSearch,
    'ey:search': eySearch,
    'deloitte:search': deloitteSearch,
    'bain:search': bainSearch,
    'bcg:search': bcgSearch,
    'hbr:search': hbrSearch,
    'hbrkorea:search': hbrkoreaSearch,
    'arg:feed': argFeed,
    'nikkei:feed': nikkeiFeed,
    'nikkei:body': nikkeiBody,
  }

  const crawlMode = crawl.crawl?.mode ?? null
  const fnguideOwned = isBusy(crawl.state) && isFnguideCrawlMode(crawlMode)

  const coverage = useCoverage(13)
  const audit = useAudit()
  const recent = useReports({
    limit: 200,
    offset: 0,
    poll: true,
  })
  const pendingCount = recent.qualityCounts.pending ?? 0
  const pendingDocsHref = `/docs/reports?${serializeReportFilters(unauditedPreset()).toString()}`
  const [recentPage, setRecentPage] = useState(0)
  const recentFiltered = useMemo(() => {
    const cutoff = Date.now() - RECENT_WINDOW_MS
    return recent.items.filter((item) => {
      if (!item.last_seen_at) return false
      const t = Date.parse(item.last_seen_at)
      return !Number.isNaN(t) && t >= cutoff
    })
  }, [recent.items])
  const recentMaxPage = Math.max(
    0,
    Math.ceil(recentFiltered.length / RECENT_PAGE_SIZE) - 1,
  )
  useEffect(() => {
    setRecentPage((p) => Math.min(p, recentMaxPage))
  }, [recentMaxPage])
  const recentOffset = recentPage * RECENT_PAGE_SIZE
  const recentPageItems = recentFiltered.slice(
    recentOffset,
    recentOffset + RECENT_PAGE_SIZE,
  )

  const countsFg = useReports({ source: 'fnguide', limit: 1, offset: 0, poll: true })
  const countsPwc = useReports({ source: 'pwc', limit: 1, offset: 0, poll: true })
  const countsAc = useReports({ source: 'accenture', limit: 1, offset: 0, poll: true })
  const countsKp = useReports({ source: 'kpmg', limit: 1, offset: 0, poll: true })
  const countsEy = useReports({ source: 'ey', limit: 1, offset: 0, poll: true })
  const countsDl = useReports({ source: 'deloitte', limit: 1, offset: 0, poll: true })
  const countsHk = useReports({ source: 'hbrkorea', limit: 1, offset: 0, poll: true })
  const countsBn = useReports({ source: 'bain', limit: 1, offset: 0, poll: true })
  const countsBcg = useReports({ source: 'bcg', limit: 1, offset: 0, poll: true })
  const countsHb = useReports({ source: 'hbr', limit: 1, offset: 0, poll: true })

  const lastDocBySource: Record<string, string | null> = {
    fnguide: countsFg.items[0]?.last_seen_at ?? null,
    pwc: countsPwc.items[0]?.last_seen_at ?? null,
    accenture: countsAc.items[0]?.last_seen_at ?? null,
    kpmg: countsKp.items[0]?.last_seen_at ?? null,
    ey: countsEy.items[0]?.last_seen_at ?? null,
    deloitte: countsDl.items[0]?.last_seen_at ?? null,
    hbrkorea: countsHk.items[0]?.last_seen_at ?? null,
    bain: countsBn.items[0]?.last_seen_at ?? null,
    bcg: countsBcg.items[0]?.last_seen_at ?? null,
    hbr: countsHb.items[0]?.last_seen_at ?? null,
  }

  const rows: RowView[] = DASHBOARD_COLLECT_JOBS.map((def) => {
    if (def.kind === 'fnguide_all_profiles') {
      const busy = fnguideOwned
      const statusLabel = fetchError
        ? 'API Offline'
        : !busy
          ? '유휴'
          : stale
            ? '응답 없음'
            : crawl.label
      const stateClass = fetchError
        ? 'offline'
        : stale && busy
          ? 'stale'
          : jobBadgeClass(!!fetchError, busy, crawl.state)
      const lastCollectedAt = busy
        ? jobTimestamp(crawl.crawl)
        : jobTimestamp(fgLatest.crawl)
      const crawlProgress = crawl.progress ?? {}
      const progressLine = busy
        ? [
            crawl.crawl?.mode
              ? crawlModeTypeLabel(crawl.crawl.mode)
              : null,
            crawl.crawl?.asset_id,
            crawlProgress.keyword != null
              ? `kw=${String(crawlProgress.keyword)}`
              : null,
            formatProgress(crawlProgress),
            status.session ? `계정 ${status.label}` : null,
          ]
            .filter(Boolean)
            .join(' · ')
        : null
      return {
        def,
        statusLabel,
        stateClass,
        lastCollectedAt,
        lastDocAt: lastDocBySource.fnguide ?? null,
        progressLine,
        busy,
        canStart: crawl.can_start === true && !busy && !fetchError,
        offline: !!fetchError,
      }
    }

    const hook = collectionByKey[def.key]
    const busy = isBusy(hook.status.state)
    const offline = !!hook.fetchError
    const progress = (hook.status.progress ??
      hook.status.job?.progress ??
      {}) as Record<string, unknown>
    let progressLine: string | null = null
    if (busy) {
      if (def.kind === 'collection_fetch_body') {
        progressLine =
          formatBodyProgress(progress) || hook.status.job?.message || '—'
      } else {
        progressLine =
          formatSearchProgress(progress) || hook.status.job?.message || '—'
      }
    }
    return {
      def,
      statusLabel: collectionStatusLabel(hook.fetchError, busy, hook.status),
      stateClass: jobBadgeClass(offline, busy, hook.status.state),
      lastCollectedAt: jobTimestamp(hook.status.job as CollectionJobRecord | null),
      lastDocAt: lastDocBySource[def.source] ?? null,
      progressLine,
      busy,
      canStart: hook.status.can_start === true && !busy && !offline,
      offline,
    }
  })

  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [requestingKeys, setRequestingKeys] = useState<Set<string>>(
    () => new Set(),
  )
  const [queueHints, setQueueHints] = useState<Record<string, string>>({})
  const [queueRunning, setQueueRunning] = useState(false)

  function toggleSelected(key: string, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (checked) next.add(key)
      else next.delete(key)
      return next
    })
  }

  function selectAll() {
    setSelected(new Set(DASHBOARD_COLLECT_JOBS.map((j) => j.key)))
  }

  function clearSelected() {
    setSelected(new Set())
  }

  function markRequesting(key: string, on: boolean) {
    setRequestingKeys((prev) => {
      const next = new Set(prev)
      if (on) next.add(key)
      else next.delete(key)
      return next
    })
  }

  async function onStartOne(def: DashboardCollectJobDef) {
    if (
      !window.confirm(
        `수집을 시작할까요?\n${startConfirmLabel(def)}\n(수집 화면 기본값)`,
      )
    ) {
      return
    }
    markRequesting(def.key, true)
    setQueueHints((h) => ({ ...h, [def.key]: '' }))
    try {
      await startDashboardJob(def.key)
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '시작 실패')
    } finally {
      markRequesting(def.key, false)
    }
  }

  async function onStopOne(def: DashboardCollectJobDef) {
    if (!window.confirm(`${def.title} ${def.jobLabel}을(를) 중단할까요?`)) {
      return
    }
    markRequesting(def.key, true)
    try {
      await stopDashboardJob(def.key)
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '중단 실패')
    } finally {
      markRequesting(def.key, false)
    }
  }

  async function onStartSelected() {
    const keys = DASHBOARD_COLLECT_JOBS.map((j) => j.key).filter((k) =>
      selected.has(k),
    )
    if (keys.length === 0) {
      window.alert('시작할 작업을 선택하세요.')
      return
    }
    const labels = keys
      .map((k) => {
        const def = DASHBOARD_COLLECT_JOBS.find((j) => j.key === k)!
        return startConfirmLabel(def)
      })
      .join('\n')
    if (
      !window.confirm(
        `선택한 ${keys.length}개 작업을 순차 시작할까요?\n(앞 작업이 끝난 뒤 다음)\n끝나면 요약 ${pendingCount}건 실행도 이어서 합니다.\n\n${labels}`,
      )
    ) {
      return
    }
    setQueueRunning(true)
    setQueueHints({})
    try {
      const result = await runDashboardStartQueue(keys, {
        onProgress: (key, phase) => {
          const label =
            phase === 'start'
              ? '큐: 시작'
              : phase === 'wait'
                ? '큐: 대기 중'
                : phase === 'skip'
                  ? '큐: 건너뜀'
                  : '큐: 실패'
          setQueueHints((h) => ({ ...h, [key]: label }))
        },
      })
      const bits: string[] = []
      if (result.started.length)
        bits.push(`시작 ${result.started.length}건`)
      if (result.skipped.length)
        bits.push(
          `건너뜀 ${result.skipped.map((s) => `${s.key}(${s.reason})`).join(', ')}`,
        )
      if (result.failed.length)
        bits.push(
          `실패 ${result.failed.map((s) => `${s.key}(${s.reason})`).join(', ')}`,
        )

      if (result.started.length > 0) {
        const ok = await audit.startPending()
        bits.push(ok ? '요약 실행 시작' : '요약 실행 못 함')
        if (ok) void recent.refresh()
      }

      if (bits.length) window.alert(bits.join('\n'))
    } finally {
      setQueueRunning(false)
    }
  }

  async function onStartPendingAudit() {
    if (
      !window.confirm(
        `요약 대기 ${pendingCount}건을 실행할까요?\n(FnGuide 품질검사 · 기타 매체 요약)`,
      )
    ) {
      return
    }
    const ok = await audit.startPending()
    if (!ok) {
      window.alert('요약 실행 실패')
      return
    }
    void recent.refresh()
  }

  async function onStopSelected() {
    const keys = DASHBOARD_COLLECT_JOBS.map((j) => j.key).filter((k) =>
      selected.has(k),
    )
    const busyKeys = keys.filter((k) => rows.find((r) => r.def.key === k)?.busy)
    if (busyKeys.length === 0) {
      window.alert('선택한 항목 중 실행 중인 작업이 없습니다.')
      return
    }
    if (
      !window.confirm(
        `실행 중인 ${busyKeys.length}개 작업을 중단할까요?`,
      )
    ) {
      return
    }
    for (const key of busyKeys) {
      markRequesting(key, true)
      try {
        await stopDashboardJob(key)
      } catch (err) {
        window.alert(
          `${key}: ${err instanceof Error ? err.message : '중단 실패'}`,
        )
      } finally {
        markRequesting(key, false)
      }
    }
  }

  return (
    <>
      <header className="monitor-header">
        <h1>운영 대시보드</h1>
        <p className="lede">
          목록에서 시작·중단할 수 있습니다. 상세 설정은 수집 화면에서 합니다.
        </p>
      </header>

      <section className="panel">
        <div className="section-head">
          <h2>수집 작업</h2>
          <span className="section-note">
            마지막 수집 · 신선도 · 기본값으로 시작
          </span>
        </div>

        <div className="collect-job-toolbar">
          <button
            type="button"
            className="run-btn"
            disabled={queueRunning || selected.size === 0}
            onClick={() => void onStartSelected()}
          >
            {queueRunning ? '순차 실행 중…' : '선택 시작'}
          </button>
          <button
            type="button"
            className="logout-btn"
            disabled={queueRunning || selected.size === 0}
            onClick={() => void onStopSelected()}
          >
            선택 중단
          </button>
          <button
            type="button"
            className="run-btn"
            disabled={queueRunning}
            onClick={selectAll}
          >
            전체 선택
          </button>
          <button
            type="button"
            className="run-btn"
            disabled={queueRunning || selected.size === 0}
            onClick={clearSelected}
          >
            선택 해제
          </button>
          <span className="section-note">{selected.size}개 선택</span>
          <span className="collect-job-toolbar-sep" aria-hidden="true" />
          <span className="section-note">
            요약 대기 {pendingCount}건
            {audit.busy
              ? ` · ${audit.label}${audit.message ? ` — ${audit.message}` : ''}`
              : ''}
          </span>
          <button
            type="button"
            className="run-btn"
            disabled={queueRunning || audit.busy || !audit.canStart}
            onClick={() => void onStartPendingAudit()}
            title="요약·품질검사 대기 건을 일괄 실행"
          >
            {audit.busy ? '요약 중…' : `요약 ${pendingCount}건 실행`}
          </button>
          <Link to={pendingDocsHref}>문서</Link>
        </div>
        {audit.error ? <p className="warn">{audit.error}</p> : null}

        <div className="collect-job-list">
          {rows.map((row) => (
            <CollectJobRow
              key={row.def.key}
              title={row.def.title}
              jobLabel={row.def.jobLabel}
              statusLabel={row.statusLabel}
              stateClass={row.stateClass}
              freshnessKind={row.def.freshnessKind}
              lastCollectedAt={row.lastCollectedAt}
              lastDocAt={row.lastDocAt}
              progressLine={row.progressLine}
              settingsPath={row.def.settingsPath}
              checked={selected.has(row.def.key)}
              onCheckedChange={(checked) =>
                toggleSelected(row.def.key, checked)
              }
              canStart={row.canStart && !queueRunning}
              canStop={row.busy}
              requesting={
                requestingKeys.has(row.def.key) ||
                (queueRunning && queueHints[row.def.key]?.startsWith('큐:') === true)
              }
              queueHint={queueHints[row.def.key] || null}
              onStart={() => void onStartOne(row.def)}
              onStop={() => void onStopOne(row.def)}
            />
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>커버리지</h2>
          <span className="section-note">발행일 기준 · 최근 13주</span>
        </div>
        <CoverageGrass
          weeks={coverage.weeks}
          sources={coverage.sources}
          error={coverage.error}
          loading={coverage.loading}
        />
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>최근 수집</h2>
          <span className="section-note">
            <Link to="/docs/reports">전체 보고서</Link>
            {' · '}
            최근 12시간
          </span>
        </div>
        {recent.error ? (
          <p className="warn">{recent.error}</p>
        ) : recentFiltered.length === 0 ? (
          <p className="empty">최근 12시간 내 수집 건이 없습니다.</p>
        ) : (
          <>
            <div className="report-sheet">
              <table className="report-table">
                <thead>
                  <tr>
                    <th className="col-provider">매체</th>
                    <th className="col-status">상태</th>
                    <th className="col-title">제목</th>
                    <th className="col-published">발행</th>
                  </tr>
                </thead>
                <tbody>
                  {recentPageItems.map((item) => (
                    <tr key={item.id}>
                      <td className="col-provider">
                        {sourceLabel(item.source)}
                      </td>
                      <td className="col-status">
                        <span className={`status-pill status-${item.status}`}>
                          {STATUS_LABEL[item.status] || item.status}
                        </span>
                      </td>
                      <td className="col-title report-title" title={item.title}>
                        {item.title}
                      </td>
                      <td className="col-published mono">
                        {formatPublishedAt(item.published_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pager">
              <button
                type="button"
                className="run-btn"
                disabled={recentPage <= 0}
                onClick={() => setRecentPage((p) => Math.max(0, p - 1))}
              >
                이전
              </button>
              <span className="section-note">
                {recentOffset + 1}–
                {Math.min(
                  recentOffset + RECENT_PAGE_SIZE,
                  recentFiltered.length,
                )}{' '}
                / {recentFiltered.length}
              </span>
              <button
                type="button"
                className="run-btn"
                disabled={
                  recentOffset + RECENT_PAGE_SIZE >= recentFiltered.length
                }
                onClick={() =>
                  setRecentPage((p) => Math.min(recentMaxPage, p + 1))
                }
              >
                다음
              </button>
            </div>
          </>
        )}
      </section>
    </>
  )
}
