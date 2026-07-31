import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CollectJobCard } from '../components/CollectJobCard'
import { CoverageGrass } from '../components/CoverageGrass'
import { useCollectionJob } from '../hooks/useCollectionJob'
import { useCoverage } from '../hooks/useCoverage'
import { useFnguideLatestCrawl } from '../hooks/useFnguideLatestCrawl'
import { useReports } from '../hooks/useReports'
import { useSessionStatus } from '../hooks/useSessionStatus'
import {
  CRAWL_CLASS,
  STATUS_LABEL,
  formatProgress,
  formatPublishedAt,
} from '../lib/format'
import { crawlModeTypeLabel, isFnguideCrawlMode } from '../lib/collectNav'
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
}

function sourceLabel(source: string | null | undefined) {
  if (!source) return '—'
  return SOURCE_LABEL[source] ?? source
}

const COUNT_KEYS_FN = [
  'downloaded',
  'blind',
  'listed',
  'no_download',
  'failed',
] as const

const COUNT_KEYS_MEDIA = [
  'downloaded',
  'listed',
  'no_download',
  'failed',
] as const

function isBusy(state: string) {
  return state === 'starting' || state === 'active' || state === 'stopping'
}

function pickArgView(
  feed: CollectionJobResponse,
  body: CollectionJobResponse,
): {
  kind: 'feed' | 'fetch_body'
  status: CollectionJobResponse
} {
  const feedBusy = isBusy(feed.state)
  const bodyBusy = isBusy(body.state)
  if (bodyBusy) return { kind: 'fetch_body', status: body }
  if (feedBusy) return { kind: 'feed', status: feed }

  const feedJob = feed.job
  const bodyJob = body.job
  const feedAt = feedJob?.started_at ? Date.parse(feedJob.started_at) : 0
  const bodyAt = bodyJob?.started_at ? Date.parse(bodyJob.started_at) : 0
  if (bodyAt > feedAt) return { kind: 'fetch_body', status: body }
  return { kind: 'feed', status: feed }
}

function jobTimestamp(
  job: { started_at?: string | null; ended_at?: string | null } | null | undefined,
): string | null {
  return job?.ended_at ?? job?.started_at ?? null
}

function formatArgProgress(
  kind: 'feed' | 'fetch_body',
  job: CollectionJobRecord | null | undefined,
  progress: Record<string, unknown>,
) {
  if (kind === 'fetch_body') {
    return [
      progress.done != null && progress.total != null
        ? `${String(progress.done)}/${String(progress.total)}`
        : null,
      progress.fetched != null ? `성공 ${String(progress.fetched)}` : null,
      progress.failed != null ? `실패 ${String(progress.failed)}` : null,
      job?.message,
    ]
      .filter(Boolean)
      .join(' · ')
  }
  return [
    progress.inserted != null ? `신규 ${String(progress.inserted)}` : null,
    progress.page != null ? `page ${String(progress.page)}` : null,
    job?.message,
  ]
    .filter(Boolean)
    .join(' · ')
}

function formatSearchProgress(progress: Record<string, unknown> | undefined) {
  if (!progress) return null
  const bits: string[] = []
  if (progress.pages_done != null)
    bits.push(`pages ${String(progress.pages_done)}`)
  if (progress.listed != null) bits.push(`listed ${String(progress.listed)}`)
  if (progress.downloaded != null)
    bits.push(`downloaded ${String(progress.downloaded)}`)
  if (progress.skipped_no_download != null)
    bits.push(`no_pdf ${String(progress.skipped_no_download)}`)
  if (progress.current_title)
    bits.push(String(progress.current_title).slice(0, 48))
  return bits.length ? bits.join(' · ') : null
}

function jobBadgeClass(
  offline: boolean,
  busy: boolean,
  state: string,
): string {
  if (offline) return 'offline'
  if (busy) {
    return (
      CRAWL_CLASS[state as keyof typeof CRAWL_CLASS] ?? 'active'
    )
  }
  return 'ended'
}

export function DashboardPage() {
  const { crawl, status, stale, fetchError, requestingStop, requestLogout } =
    useSessionStatus()
  const fgLatest = useFnguideLatestCrawl()
  const argFeed = useCollectionJob({ source: 'arg', capability: 'feed' })
  const argBody = useCollectionJob({
    source: 'arg',
    capability: 'fetch_body',
  })
  const pwcSearch = useCollectionJob({ source: 'pwc', capability: 'search' })
  const accentureSearch = useCollectionJob({
    source: 'accenture',
    capability: 'search',
  })
  const kpmgSearch = useCollectionJob({
    source: 'kpmg',
    capability: 'search',
  })
  const eySearch = useCollectionJob({
    source: 'ey',
    capability: 'search',
  })
  const deloitteSearch = useCollectionJob({
    source: 'deloitte',
    capability: 'search',
  })
  const hbrkoreaSearch = useCollectionJob({
    source: 'hbrkorea',
    capability: 'search',
  })
  const mckinseySearch = useCollectionJob({
    source: 'mckinsey',
    capability: 'search',
  })
  const bainSearch = useCollectionJob({
    source: 'bain',
    capability: 'search',
  })
  const bcgSearch = useCollectionJob({
    source: 'bcg',
    capability: 'search',
  })
  const hbrSearch = useCollectionJob({
    source: 'hbr',
    capability: 'search',
  })

  const crawlMode = crawl.crawl?.mode ?? null
  const fnguideOwned =
    isBusy(crawl.state) && isFnguideCrawlMode(crawlMode)
  const pwcAdhoc =
    isBusy(crawl.state) && crawlMode === 'pwc'
  const accentureAdhoc =
    isBusy(crawl.state) && crawlMode === 'accenture'
  const kpmgAdhoc =
    isBusy(crawl.state) && crawlMode === 'kpmg'
  const eyAdhoc = isBusy(crawl.state) && crawlMode === 'ey'
  const deloitteAdhoc = isBusy(crawl.state) && crawlMode === 'deloitte'
  const mckinseyAdhoc = isBusy(crawl.state) && crawlMode === 'mckinsey'
  const bainAdhoc = isBusy(crawl.state) && crawlMode === 'bain'
  const bcgAdhoc = isBusy(crawl.state) && crawlMode === 'bcg'
  const hbrAdhoc = isBusy(crawl.state) && crawlMode === 'hbr'
  const hbrkoreaAdhoc = isBusy(crawl.state) && crawlMode === 'hbrkorea'
  const nikkeiAdhoc = isBusy(crawl.state) && crawlMode === 'nikkei'
  const nikkeixtechAdhoc = isBusy(crawl.state) && crawlMode === 'nikkeixtech'

  const argView = pickArgView(argFeed.status, argBody.status)
  const argActive = argView.kind === 'fetch_body' ? argBody : argFeed
  const argBusy = isBusy(argView.status.state)
  const pwcSearchBusy = isBusy(pwcSearch.status.state)
  const accentureSearchBusy = isBusy(accentureSearch.status.state)
  const kpmgSearchBusy = isBusy(kpmgSearch.status.state)
  const eySearchBusy = isBusy(eySearch.status.state)
  const deloitteSearchBusy = isBusy(deloitteSearch.status.state)
  const hbrkoreaSearchBusy = isBusy(hbrkoreaSearch.status.state)
  const mckinseySearchBusy = isBusy(mckinseySearch.status.state)
  const bainSearchBusy = isBusy(bainSearch.status.state)
  const bcgSearchBusy = isBusy(bcgSearch.status.state)
  const hbrSearchBusy = isBusy(hbrSearch.status.state)
  const pwcBusy = pwcSearchBusy || pwcAdhoc
  const accentureBusy = accentureSearchBusy || accentureAdhoc
  const kpmgBusy = kpmgSearchBusy || kpmgAdhoc
  const eyBusy = eySearchBusy || eyAdhoc
  const deloitteBusy = deloitteSearchBusy || deloitteAdhoc
  const mckinseyBusy = mckinseySearchBusy || mckinseyAdhoc
  const bainBusy = bainSearchBusy || bainAdhoc
  const bcgBusy = bcgSearchBusy || bcgAdhoc
  const hbrBusy = hbrSearchBusy || hbrAdhoc
  const hbrkoreaBusy = hbrkoreaSearchBusy || hbrkoreaAdhoc
  const nikkeiBusy = nikkeiAdhoc
  const nikkeixtechBusy = nikkeixtechAdhoc

  const crawlProgress = crawl.progress ?? {}
  const pwcProgress = (pwcSearch.status.progress ??
    pwcSearch.status.job?.progress ??
    {}) as Record<string, unknown>
  const accentureProgress = (accentureSearch.status.progress ??
    accentureSearch.status.job?.progress ??
    {}) as Record<string, unknown>
  const kpmgProgress = (kpmgSearch.status.progress ??
    kpmgSearch.status.job?.progress ??
    {}) as Record<string, unknown>
  const eyProgress = (eySearch.status.progress ??
    eySearch.status.job?.progress ??
    {}) as Record<string, unknown>
  const deloitteProgress = (deloitteSearch.status.progress ??
    deloitteSearch.status.job?.progress ??
    {}) as Record<string, unknown>
  const hbrkoreaProgress = (hbrkoreaSearch.status.progress ??
    hbrkoreaSearch.status.job?.progress ??
    {}) as Record<string, unknown>
  const mckinseyProgress = (mckinseySearch.status.progress ??
    mckinseySearch.status.job?.progress ??
    {}) as Record<string, unknown>
  const bainProgress = (bainSearch.status.progress ??
    bainSearch.status.job?.progress ??
    {}) as Record<string, unknown>
  const bcgProgress = (bcgSearch.status.progress ??
    bcgSearch.status.job?.progress ??
    {}) as Record<string, unknown>
  const hbrProgress = (hbrSearch.status.progress ??
    hbrSearch.status.job?.progress ??
    {}) as Record<string, unknown>
  const argProgress = (argView.status.progress ??
    argView.status.job?.progress ??
    {}) as Record<string, unknown>

  const coverage = useCoverage(13)
  const recent = useReports({
    limit: 200,
    offset: 0,
    poll: true,
  })
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
  const countsFg = useReports({
    source: 'fnguide',
    limit: 1,
    offset: 0,
    poll: true,
  })
  const countsPwc = useReports({
    source: 'pwc',
    limit: 1,
    offset: 0,
    poll: true,
  })
  const countsAc = useReports({
    source: 'accenture',
    limit: 1,
    offset: 0,
    poll: true,
  })
  const countsKp = useReports({
    source: 'kpmg',
    limit: 1,
    offset: 0,
    poll: true,
  })
  const countsEy = useReports({
    source: 'ey',
    limit: 1,
    offset: 0,
    poll: true,
  })
  const countsDl = useReports({
    source: 'deloitte',
    limit: 1,
    offset: 0,
    poll: true,
  })
  const countsHk = useReports({
    source: 'hbrkorea',
    limit: 1,
    offset: 0,
    poll: true,
  })
  const countsMk = useReports({
    source: 'mckinsey',
    limit: 1,
    offset: 0,
    poll: true,
  })
  const countsBn = useReports({
    source: 'bain',
    limit: 1,
    offset: 0,
    poll: true,
  })
  const countsBcg = useReports({
    source: 'bcg',
    limit: 1,
    offset: 0,
    poll: true,
  })
  const countsHb = useReports({
    source: 'hbr',
    limit: 1,
    offset: 0,
    poll: true,
  })

  const fnguideBadge = fetchError
    ? 'offline'
    : stale && fnguideOwned
      ? 'stale'
      : jobBadgeClass(!!fetchError, fnguideOwned, crawl.state)
  const argOffline = !!(argFeed.fetchError || argBody.fetchError)
  const argBadge = jobBadgeClass(
    argOffline,
    argBusy,
    argView.status.state,
  )
  const pwcBadge = jobBadgeClass(
    !!(pwcSearch.fetchError || (pwcAdhoc && fetchError)),
    pwcBusy,
    pwcSearchBusy ? pwcSearch.status.state : crawl.state,
  )
  const accentureBadge = jobBadgeClass(
    !!(accentureSearch.fetchError || (accentureAdhoc && fetchError)),
    accentureBusy,
    accentureSearchBusy ? accentureSearch.status.state : crawl.state,
  )
  const kpmgBadge = jobBadgeClass(
    !!(kpmgSearch.fetchError || (kpmgAdhoc && fetchError)),
    kpmgBusy,
    kpmgSearchBusy ? kpmgSearch.status.state : crawl.state,
  )
  const eyBadge = jobBadgeClass(
    !!(eySearch.fetchError || (eyAdhoc && fetchError)),
    eyBusy,
    eySearchBusy ? eySearch.status.state : crawl.state,
  )
  const deloitteBadge = jobBadgeClass(
    !!(deloitteSearch.fetchError || (deloitteAdhoc && fetchError)),
    deloitteBusy,
    deloitteSearchBusy ? deloitteSearch.status.state : crawl.state,
  )
  const mckinseyBadge = jobBadgeClass(
    !!(mckinseySearch.fetchError || (mckinseyAdhoc && fetchError)),
    mckinseyBusy,
    mckinseySearchBusy ? mckinseySearch.status.state : crawl.state,
  )
  const bainBadge = jobBadgeClass(
    !!(bainSearch.fetchError || (bainAdhoc && fetchError)),
    bainBusy,
    bainSearchBusy ? bainSearch.status.state : crawl.state,
  )
  const bcgBadge = jobBadgeClass(
    !!(bcgSearch.fetchError || (bcgAdhoc && fetchError)),
    bcgBusy,
    bcgSearchBusy ? bcgSearch.status.state : crawl.state,
  )
  const hbrBadge = jobBadgeClass(
    !!(hbrSearch.fetchError || (hbrAdhoc && fetchError)),
    hbrBusy,
    hbrSearchBusy ? hbrSearch.status.state : crawl.state,
  )
  const hbrkoreaBadge = jobBadgeClass(
    !!(hbrkoreaSearch.fetchError || (hbrkoreaAdhoc && fetchError)),
    hbrkoreaBusy,
    hbrkoreaSearchBusy ? hbrkoreaSearch.status.state : crawl.state,
  )
  const nikkeixtechBadge = jobBadgeClass(
    !!(nikkeixtechAdhoc && fetchError),
    nikkeixtechBusy,
    crawl.state,
  )
  const nikkeiBadge = jobBadgeClass(
    !!(nikkeiAdhoc && fetchError),
    nikkeiBusy,
    crawl.state,
  )

  async function onStopFnguide() {
    if (!window.confirm('FnGuide 크롤을 종료하고 로그아웃할까요?')) return
    try {
      await requestLogout()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '종료 요청 실패')
    }
  }

  async function onStopArg() {
    const label =
      argView.kind === 'fetch_body' ? 'ARG 본문 채우기' : 'ARG 피드'
    if (!window.confirm(`${label} 잡을 중단할까요?`)) return
    try {
      await argActive.stopFeed()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '중단 실패')
    }
  }

  async function onStopMedia(
    source:
      | 'pwc'
      | 'accenture'
      | 'kpmg'
      | 'ey'
      | 'deloitte'
      | 'mckinsey'
      | 'bain'
      | 'bcg'
      | 'hbr'
      | 'hbrkorea'
      | 'nikkeixtech'
      | 'nikkei',
    searchBusy: boolean,
    adhoc: boolean,
    stopSearch?: () => Promise<unknown>,
  ) {
    if (searchBusy) {
      if (!stopSearch) return
      if (!window.confirm(`${source} 검색 작업을 중단할까요?`)) return
      try {
        await stopSearch()
      } catch (err) {
        window.alert(err instanceof Error ? err.message : '중단 실패')
      }
      return
    }
    if (adhoc) {
      if (!window.confirm(`${source} 애드혹 브라우저를 종료할까요?`)) return
      try {
        await requestLogout()
      } catch (err) {
        window.alert(err instanceof Error ? err.message : '종료 요청 실패')
      }
    }
  }

  const fnguideValue = fetchError
    ? 'API Offline'
    : !fnguideOwned
      ? '유휴'
      : stale
        ? '응답 없음'
        : crawl.label

  const pwcValue = pwcSearch.fetchError
    ? 'API Offline'
    : pwcSearchBusy
      ? pwcSearch.status.label
      : pwcAdhoc
        ? crawl.label
        : pwcSearch.status.job
          ? pwcSearch.status.label
          : '유휴'

  const accentureValue = accentureSearch.fetchError
    ? 'API Offline'
    : accentureSearchBusy
      ? accentureSearch.status.label
      : accentureAdhoc
        ? crawl.label
        : accentureSearch.status.job
          ? accentureSearch.status.label
          : '유휴'

  const kpmgValue = kpmgSearch.fetchError
    ? 'API Offline'
    : kpmgSearchBusy
      ? kpmgSearch.status.label
      : kpmgAdhoc
        ? crawl.label
        : kpmgSearch.status.job
          ? kpmgSearch.status.label
          : '유휴'

  const eyValue = eySearch.fetchError
    ? 'API Offline'
    : eySearchBusy
      ? eySearch.status.label
      : eyAdhoc
        ? crawl.label
        : eySearch.status.job
          ? eySearch.status.label
          : '유휴'

  const deloitteValue = deloitteSearch.fetchError
    ? 'API Offline'
    : deloitteSearchBusy
      ? deloitteSearch.status.label
      : deloitteAdhoc
        ? crawl.label
        : deloitteSearch.status.job
          ? deloitteSearch.status.label
          : '유휴'

  const hbrValue = hbrSearch.fetchError
    ? 'API Offline'
    : hbrSearchBusy
      ? hbrSearch.status.label
      : hbrAdhoc
        ? crawl.label
        : hbrSearch.status.job
          ? hbrSearch.status.label
          : '유휴'

  const hbrkoreaValue = hbrkoreaSearch.fetchError
    ? 'API Offline'
    : hbrkoreaSearchBusy
      ? hbrkoreaSearch.status.label
      : hbrkoreaAdhoc
        ? crawl.label
        : hbrkoreaSearch.status.job
          ? hbrkoreaSearch.status.label
          : '유휴'

  const mckinseyValue = mckinseySearch.fetchError
    ? 'API Offline'
    : mckinseySearchBusy
      ? mckinseySearch.status.label
      : mckinseyAdhoc
        ? crawl.label
        : mckinseySearch.status.job
          ? mckinseySearch.status.label
          : '유휴'

  const bainValue = bainSearch.fetchError
    ? 'API Offline'
    : bainSearchBusy
      ? bainSearch.status.label
      : bainAdhoc
        ? crawl.label
        : bainSearch.status.job
          ? bainSearch.status.label
          : '유휴'

  const bcgValue = bcgSearch.fetchError
    ? 'API Offline'
    : bcgSearchBusy
      ? bcgSearch.status.label
      : bcgAdhoc
        ? crawl.label
        : bcgSearch.status.job
          ? bcgSearch.status.label
          : '유휴'

  const nikkeixtechValue = fetchError
    ? 'API Offline'
    : nikkeixtechAdhoc
      ? crawl.label
      : '유휴'

  const nikkeiValue = fetchError
    ? 'API Offline'
    : nikkeiAdhoc
      ? crawl.label
      : '유휴'

  const fnguideLastAt = fnguideOwned
    ? jobTimestamp(crawl.crawl)
    : jobTimestamp(fgLatest.crawl)
  const fnguideProgress = fnguideOwned
    ? [
        crawl.crawl?.asset_id,
        crawlProgress.keyword != null
          ? `kw=${String(crawlProgress.keyword)}`
          : null,
        formatProgress(crawlProgress),
      ]
        .filter(Boolean)
        .join(' · ')
    : null

  function mediaLastAt(
    searchJob: CollectionJobRecord | null | undefined,
    adhoc: boolean,
  ) {
    const fromJob = jobTimestamp(searchJob)
    if (fromJob) return fromJob
    if (adhoc) return jobTimestamp(crawl.crawl)
    return null
  }

  function mediaProgress(
    searchBusy: boolean,
    adhoc: boolean,
    progress: Record<string, unknown>,
    message: string | null | undefined,
  ) {
    if (searchBusy) {
      return formatSearchProgress(progress) || message || '—'
    }
    if (adhoc) {
      const bits = [
        typeof crawlProgress.url === 'string' ? crawlProgress.url : null,
        crawl.crawl?.cdp_port != null
          ? `CDP ${crawl.crawl.cdp_port}`
          : null,
        formatProgress(crawlProgress),
      ].filter(Boolean)
      return bits.length ? bits.join(' · ') : null
    }
    return null
  }

  return (
    <>
      <header className="monitor-header">
        <h1>운영 대시보드</h1>
        <p className="lede">
          매체별 수집 상태와 최근 결과입니다. 시작은 각 수집 화면에서 합니다.
        </p>
      </header>

      <section className="panel">
        <div className="section-head">
          <h2>수집 작업</h2>
          <span className="section-note">
            마지막 수집 · 신선도 · 계정/산출물
          </span>
        </div>

        <div className="job-board">
            <CollectJobCard
              title="FnGuide"
              meta={[
                '계정',
                '리포트',
                '검색',
                fnguideOwned ? crawlModeTypeLabel(crawlMode) : '',
              ]}
              statusLabel={fnguideValue}
              stateClass={fnguideBadge}
              freshnessKind="report"
              lastCollectedAt={fnguideLastAt}
              lastDocAt={countsFg.items[0]?.last_seen_at ?? null}
              accountLine={`계정 ${fetchError ? '—' : status.label}`}
              progressLine={fnguideProgress}
              links={
                <>
                  <Link to="/collect/fnguide/list/search">검색 실행</Link>
                  {' · '}
                  <Link to="/docs/reports/fnguide">보고서</Link>
                </>
              }
              stop={
                fnguideOwned
                  ? {
                      label: requestingStop ? '요청 중…' : '종료',
                      disabled: requestingStop || !!fetchError,
                      onClick: () => void onStopFnguide(),
                    }
                  : null
              }
            />
            <CollectJobCard
              title="PwC"
              meta={['무계정', '리포트', '검색', pwcAdhoc ? '애드혹' : '']}
              statusLabel={pwcValue}
              stateClass={pwcBadge}
              freshnessKind="report"
              lastCollectedAt={mediaLastAt(pwcSearch.status.job, pwcAdhoc)}
              lastDocAt={countsPwc.items[0]?.last_seen_at ?? null}
              progressLine={mediaProgress(
                pwcSearchBusy,
                pwcAdhoc,
                pwcProgress,
                pwcSearch.status.job?.message,
              )}
              links={
                <>
                  <Link to="/collect/pwc/list/search">검색 실행</Link>
                  {' · '}
                  <Link to="/docs/reports/pwc">보고서</Link>
                </>
              }
              stop={
                pwcBusy
                  ? {
                      label: (pwcSearchBusy
                        ? pwcSearch.requestingStop
                        : requestingStop)
                        ? '요청 중…'
                        : pwcSearchBusy
                          ? '검색 중단'
                          : '애드혹 종료',
                      disabled: pwcSearchBusy
                        ? pwcSearch.requestingStop
                        : requestingStop || !!fetchError,
                      onClick: () =>
                        void onStopMedia(
                          'pwc',
                          pwcSearchBusy,
                          pwcAdhoc,
                          () => pwcSearch.stopFeed(),
                        ),
                    }
                  : null
              }
            />
            <CollectJobCard
              title="Accenture"
              meta={[
                '무계정',
                '리포트',
                '검색',
                accentureAdhoc ? '애드혹' : '',
              ]}
              statusLabel={accentureValue}
              stateClass={accentureBadge}
              freshnessKind="report"
              lastCollectedAt={mediaLastAt(
                accentureSearch.status.job,
                accentureAdhoc,
              )}
              lastDocAt={countsAc.items[0]?.last_seen_at ?? null}
              progressLine={mediaProgress(
                accentureSearchBusy,
                accentureAdhoc,
                accentureProgress,
                accentureSearch.status.job?.message,
              )}
              links={
                <>
                  <Link to="/collect/accenture/list/search">검색 실행</Link>
                  {' · '}
                  <Link to="/docs/reports/accenture">보고서</Link>
                </>
              }
              stop={
                accentureBusy
                  ? {
                      label: (accentureSearchBusy
                        ? accentureSearch.requestingStop
                        : requestingStop)
                        ? '요청 중…'
                        : accentureSearchBusy
                          ? '검색 중단'
                          : '애드혹 종료',
                      disabled: accentureSearchBusy
                        ? accentureSearch.requestingStop
                        : requestingStop || !!fetchError,
                      onClick: () =>
                        void onStopMedia(
                          'accenture',
                          accentureSearchBusy,
                          accentureAdhoc,
                          () => accentureSearch.stopFeed(),
                        ),
                    }
                  : null
              }
            />
            <CollectJobCard
              title="KPMG"
              meta={['무계정', '리포트', '검색', kpmgAdhoc ? '애드혹' : '']}
              statusLabel={kpmgValue}
              stateClass={kpmgBadge}
              freshnessKind="report"
              lastCollectedAt={mediaLastAt(kpmgSearch.status.job, kpmgAdhoc)}
              lastDocAt={countsKp.items[0]?.last_seen_at ?? null}
              progressLine={mediaProgress(
                kpmgSearchBusy,
                kpmgAdhoc,
                kpmgProgress,
                kpmgSearch.status.job?.message,
              )}
              links={
                <>
                  <Link to="/collect/kpmg/list/search">검색 실행</Link>
                  {' · '}
                  <Link to="/docs/reports/kpmg">보고서</Link>
                </>
              }
              stop={
                kpmgBusy
                  ? {
                      label: (kpmgSearchBusy
                        ? kpmgSearch.requestingStop
                        : requestingStop)
                        ? '요청 중…'
                        : kpmgSearchBusy
                          ? '검색 중단'
                          : '애드혹 종료',
                      disabled: kpmgSearchBusy
                        ? kpmgSearch.requestingStop
                        : requestingStop || !!fetchError,
                      onClick: () =>
                        void onStopMedia(
                          'kpmg',
                          kpmgSearchBusy,
                          kpmgAdhoc,
                          () => kpmgSearch.stopFeed(),
                        ),
                    }
                  : null
              }
            />
            <CollectJobCard
              title="EY"
              meta={['무계정', '리포트', '검색', eyAdhoc ? '애드혹' : '']}
              statusLabel={eyValue}
              stateClass={eyBadge}
              freshnessKind="report"
              lastCollectedAt={mediaLastAt(eySearch.status.job, eyAdhoc)}
              lastDocAt={countsEy.items[0]?.last_seen_at ?? null}
              progressLine={mediaProgress(
                eySearchBusy,
                eyAdhoc,
                eyProgress,
                eySearch.status.job?.message,
              )}
              links={
                <>
                  <Link to="/collect/ey/list/search">검색 실행</Link>
                  {' · '}
                  <Link to="/docs/reports/ey">보고서</Link>
                </>
              }
              stop={
                eyBusy
                  ? {
                      label: (eySearchBusy
                        ? eySearch.requestingStop
                        : requestingStop)
                        ? '요청 중…'
                        : eySearchBusy
                          ? '검색 중단'
                          : '애드혹 종료',
                      disabled: eySearchBusy
                        ? eySearch.requestingStop
                        : requestingStop || !!fetchError,
                      onClick: () =>
                        void onStopMedia(
                          'ey',
                          eySearchBusy,
                          eyAdhoc,
                          () => eySearch.stopFeed(),
                        ),
                    }
                  : null
              }
            />
            <CollectJobCard
              title="Deloitte"
              meta={[
                '무계정',
                '리포트',
                '검색',
                deloitteAdhoc ? '애드혹' : '',
              ]}
              statusLabel={deloitteValue}
              stateClass={deloitteBadge}
              freshnessKind="report"
              lastCollectedAt={mediaLastAt(
                deloitteSearch.status.job,
                deloitteAdhoc,
              )}
              lastDocAt={countsDl.items[0]?.last_seen_at ?? null}
              progressLine={mediaProgress(
                deloitteSearchBusy,
                deloitteAdhoc,
                deloitteProgress,
                deloitteSearch.status.job?.message,
              )}
              links={
                <>
                  <Link to="/collect/deloitte/list/search">검색 실행</Link>
                  {' · '}
                  <Link to="/docs/reports/deloitte">보고서</Link>
                </>
              }
              stop={
                deloitteBusy
                  ? {
                      label: (deloitteSearchBusy
                        ? deloitteSearch.requestingStop
                        : requestingStop)
                        ? '요청 중…'
                        : deloitteSearchBusy
                          ? '검색 중단'
                          : '애드혹 종료',
                      disabled: deloitteSearchBusy
                        ? deloitteSearch.requestingStop
                        : requestingStop || !!fetchError,
                      onClick: () =>
                        void onStopMedia(
                          'deloitte',
                          deloitteSearchBusy,
                          deloitteAdhoc,
                          () => deloitteSearch.stopFeed(),
                        ),
                    }
                  : null
              }
            />
            <CollectJobCard
              title="McKinsey"
              meta={[
                '무계정',
                '리포트',
                '검색',
                mckinseyAdhoc ? '애드혹' : '',
              ]}
              statusLabel={mckinseyValue}
              stateClass={mckinseyBadge}
              freshnessKind="report"
              lastCollectedAt={mediaLastAt(
                mckinseySearch.status.job,
                mckinseyAdhoc,
              )}
              lastDocAt={countsMk.items[0]?.last_seen_at ?? null}
              progressLine={mediaProgress(
                mckinseySearchBusy,
                mckinseyAdhoc,
                mckinseyProgress,
                mckinseySearch.status.job?.message,
              )}
              links={
                <>
                  <Link to="/collect/mckinsey/list/search">검색 실행</Link>
                  {' · '}
                  <Link to="/docs/reports/mckinsey">보고서</Link>
                </>
              }
              stop={
                mckinseyBusy
                  ? {
                      label: (mckinseySearchBusy
                        ? mckinseySearch.requestingStop
                        : requestingStop)
                        ? '요청 중…'
                        : mckinseySearchBusy
                          ? '검색 중단'
                          : '애드혹 종료',
                      disabled: mckinseySearchBusy
                        ? mckinseySearch.requestingStop
                        : requestingStop || !!fetchError,
                      onClick: () =>
                        void onStopMedia(
                          'mckinsey',
                          mckinseySearchBusy,
                          mckinseyAdhoc,
                          () => mckinseySearch.stopFeed(),
                        ),
                    }
                  : null
              }
            />
            <CollectJobCard
              title="Bain"
              meta={[
                '무계정',
                '리포트',
                '검색',
                bainAdhoc ? '애드혹' : '',
              ]}
              statusLabel={bainValue}
              stateClass={bainBadge}
              freshnessKind="report"
              lastCollectedAt={mediaLastAt(
                bainSearch.status.job,
                bainAdhoc,
              )}
              lastDocAt={countsBn.items[0]?.last_seen_at ?? null}
              progressLine={mediaProgress(
                bainSearchBusy,
                bainAdhoc,
                bainProgress,
                bainSearch.status.job?.message,
              )}
              links={
                <>
                  <Link to="/collect/bain/list/search">검색 실행</Link>
                  {' · '}
                  <Link to="/docs/reports/bain">보고서</Link>
                </>
              }
              stop={
                bainBusy
                  ? {
                      label: (bainSearchBusy
                        ? bainSearch.requestingStop
                        : requestingStop)
                        ? '요청 중…'
                        : bainSearchBusy
                          ? '검색 중단'
                          : '애드혹 종료',
                      disabled: bainSearchBusy
                        ? bainSearch.requestingStop
                        : requestingStop || !!fetchError,
                      onClick: () =>
                        void onStopMedia(
                          'bain',
                          bainSearchBusy,
                          bainAdhoc,
                          () => bainSearch.stopFeed(),
                        ),
                    }
                  : null
              }
            />
            <CollectJobCard
              title="BCG"
              meta={[
                '무계정',
                '리포트',
                '검색',
                bcgAdhoc ? '애드혹' : '',
              ]}
              statusLabel={bcgValue}
              stateClass={bcgBadge}
              freshnessKind="report"
              lastCollectedAt={mediaLastAt(
                bcgSearch.status.job,
                bcgAdhoc,
              )}
              lastDocAt={countsBcg.items[0]?.last_seen_at ?? null}
              progressLine={mediaProgress(
                bcgSearchBusy,
                bcgAdhoc,
                bcgProgress,
                bcgSearch.status.job?.message,
              )}
              links={
                <>
                  <Link to="/collect/bcg/list/search">검색 실행</Link>
                  {' · '}
                  <Link to="/docs/reports/bcg">보고서</Link>
                </>
              }
              stop={
                bcgBusy
                  ? {
                      label: (bcgSearchBusy
                        ? bcgSearch.requestingStop
                        : requestingStop)
                        ? '요청 중…'
                        : bcgSearchBusy
                          ? '검색 중단'
                          : '애드혹 종료',
                      disabled: bcgSearchBusy
                        ? bcgSearch.requestingStop
                        : requestingStop || !!fetchError,
                      onClick: () =>
                        void onStopMedia(
                          'bcg',
                          bcgSearchBusy,
                          bcgAdhoc,
                          () => bcgSearch.stopFeed(),
                        ),
                    }
                  : null
              }
            />
            <CollectJobCard
              title="HBR"
              meta={[
                '계정',
                '리포트',
                '검색',
                hbrAdhoc ? '애드혹' : '',
              ]}
              statusLabel={hbrValue}
              stateClass={hbrBadge}
              freshnessKind="report"
              lastCollectedAt={mediaLastAt(hbrSearch.status.job, hbrAdhoc)}
              lastDocAt={countsHb.items[0]?.last_seen_at ?? null}
              progressLine={mediaProgress(
                hbrSearchBusy,
                hbrAdhoc,
                hbrProgress,
                hbrSearch.status.job?.message,
              )}
              links={
                <>
                  <Link to="/collect/hbr/list/search">검색 실행</Link>
                  {' · '}
                  <Link to="/docs/reports/hbr">보고서</Link>
                </>
              }
              stop={
                hbrBusy
                  ? {
                      label: (hbrSearchBusy
                        ? hbrSearch.requestingStop
                        : requestingStop)
                        ? '요청 중…'
                        : hbrSearchBusy
                          ? '검색 중단'
                          : '애드혹 종료',
                      disabled: hbrSearchBusy
                        ? hbrSearch.requestingStop
                        : requestingStop || !!fetchError,
                      onClick: () =>
                        void onStopMedia(
                          'hbr',
                          hbrSearchBusy,
                          hbrAdhoc,
                          () => hbrSearch.stopFeed(),
                        ),
                    }
                  : null
              }
            />
            <CollectJobCard
              title="HBR Korea"
              meta={[
                '계정',
                '리포트',
                '검색',
                hbrkoreaAdhoc ? '애드혹' : '',
              ]}
              statusLabel={hbrkoreaValue}
              stateClass={hbrkoreaBadge}
              freshnessKind="report"
              lastCollectedAt={mediaLastAt(
                hbrkoreaSearch.status.job,
                hbrkoreaAdhoc,
              )}
              lastDocAt={countsHk.items[0]?.last_seen_at ?? null}
              progressLine={mediaProgress(
                hbrkoreaSearchBusy,
                hbrkoreaAdhoc,
                hbrkoreaProgress,
                hbrkoreaSearch.status.job?.message,
              )}
              links={
                <>
                  <Link to="/collect/hbrkorea/list/search">검색 실행</Link>
                  {' · '}
                  <Link to="/docs/reports/hbrkorea">보고서</Link>
                </>
              }
              stop={
                hbrkoreaBusy
                  ? {
                      label: (hbrkoreaSearchBusy
                        ? hbrkoreaSearch.requestingStop
                        : requestingStop)
                        ? '요청 중…'
                        : hbrkoreaSearchBusy
                          ? '검색 중단'
                          : '애드혹 종료',
                      disabled: hbrkoreaSearchBusy
                        ? hbrkoreaSearch.requestingStop
                        : requestingStop || !!fetchError,
                      onClick: () =>
                        void onStopMedia(
                          'hbrkorea',
                          hbrkoreaSearchBusy,
                          hbrkoreaAdhoc,
                          () => hbrkoreaSearch.stopFeed(),
                        ),
                    }
                  : null
              }
            />
            <CollectJobCard
              title="Nikkei xTECH"
              meta={[
                '계정',
                '애드혹',
                nikkeixtechAdhoc ? '로그인' : '',
              ]}
              statusLabel={nikkeixtechValue}
              stateClass={nikkeixtechBadge}
              freshnessKind="article"
              lastCollectedAt={
                nikkeixtechAdhoc ? jobTimestamp(crawl.crawl) : null
              }
              progressLine={
                nikkeixtechAdhoc
                  ? mediaProgress(
                      false,
                      true,
                      crawlProgress,
                      crawl.crawl?.message,
                    )
                  : null
              }
              links={
                <>
                  <Link to="/collect/nikkeixtech/list/search">
                    애드혹 실행
                  </Link>
                </>
              }
              stop={
                nikkeixtechBusy
                  ? {
                      label: requestingStop ? '요청 중…' : '애드혹 종료',
                      disabled: requestingStop || !!fetchError,
                      onClick: () =>
                        void onStopMedia(
                          'nikkeixtech',
                          false,
                          nikkeixtechAdhoc,
                        ),
                    }
                  : null
              }
            />
            <CollectJobCard
              title="Nikkei"
              meta={['계정', '애드혹', nikkeiAdhoc ? '로그인' : '']}
              statusLabel={nikkeiValue}
              stateClass={nikkeiBadge}
              freshnessKind="article"
              lastCollectedAt={
                nikkeiAdhoc ? jobTimestamp(crawl.crawl) : null
              }
              progressLine={
                nikkeiAdhoc
                  ? mediaProgress(
                      false,
                      true,
                      crawlProgress,
                      crawl.crawl?.message,
                    )
                  : null
              }
              links={
                <>
                  <Link to="/collect/nikkei/list/search">애드혹 실행</Link>
                </>
              }
              stop={
                nikkeiBusy
                  ? {
                      label: requestingStop ? '요청 중…' : '애드혹 종료',
                      disabled: requestingStop || !!fetchError,
                      onClick: () =>
                        void onStopMedia('nikkei', false, nikkeiAdhoc),
                    }
                  : null
              }
            />
            <CollectJobCard
              title="ARG"
              meta={[
                '무계정',
                '일간지',
                argView.kind === 'fetch_body' ? '본문' : '피드',
              ]}
              statusLabel={
                argOffline
                  ? 'API Offline'
                  : argBusy
                    ? argView.status.label
                    : argView.status.job
                      ? argView.status.label
                      : '유휴'
              }
              stateClass={argBadge}
              freshnessKind="daily"
              lastCollectedAt={jobTimestamp(argView.status.job)}
              progressLine={
                argBusy || argView.status.job?.message
                  ? formatArgProgress(
                      argView.kind,
                      argView.status.job,
                      argProgress,
                    ) || null
                  : null
              }
              links={
                <>
                  <Link to="/collect/arg/list/feed">피드</Link>
                  {' · '}
                  <Link to="/collect/arg/body/fetch">본문</Link>
                  {' · '}
                  <Link to="/docs/articles">기사</Link>
                </>
              }
              stop={
                argBusy
                  ? {
                      label: argActive.requestingStop ? '요청 중…' : '중단',
                      disabled: argActive.requestingStop,
                      onClick: () => void onStopArg(),
                    }
                  : null
              }
            />
        </div>
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>커버리지</h2>
          <span className="section-note">
            발행일 기준 · 최근 13주
          </span>
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
                {Math.min(recentOffset + RECENT_PAGE_SIZE, recentFiltered.length)}{' '}
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

      <section className="panel">
        <div className="section-head">
          <h2>문서 카운트</h2>
          <span className="section-note">Docs 탭으로 이동</span>
        </div>
        <div className="dash-count-rows">
          <CountRow
            label="FnGuide"
            source="fnguide"
            counts={countsFg.counts}
            keys={COUNT_KEYS_FN}
            error={countsFg.error}
            total={countsFg.counts.all ?? 0}
          />
          <CountRow
            label="PwC"
            source="pwc"
            counts={countsPwc.counts}
            keys={COUNT_KEYS_MEDIA}
            error={countsPwc.error}
            total={countsPwc.counts.all ?? 0}
          />
          <CountRow
            label="Accenture"
            source="accenture"
            counts={countsAc.counts}
            keys={COUNT_KEYS_MEDIA}
            error={countsAc.error}
            total={countsAc.counts.all ?? 0}
          />
          <CountRow
            label="KPMG"
            source="kpmg"
            counts={countsKp.counts}
            keys={COUNT_KEYS_MEDIA}
            error={countsKp.error}
            total={countsKp.counts.all ?? 0}
          />
          <CountRow
            label="EY"
            source="ey"
            counts={countsEy.counts}
            keys={COUNT_KEYS_MEDIA}
            error={countsEy.error}
            total={countsEy.counts.all ?? 0}
          />
          <CountRow
            label="Deloitte"
            source="deloitte"
            counts={countsDl.counts}
            keys={COUNT_KEYS_MEDIA}
            error={countsDl.error}
            total={countsDl.counts.all ?? 0}
          />
          <CountRow
            label="HBR Korea"
            source="hbrkorea"
            counts={countsHk.counts}
            keys={COUNT_KEYS_MEDIA}
            error={countsHk.error}
            total={countsHk.counts.all ?? 0}
          />
        </div>
      </section>
    </>
  )
}

function CountRow({
  label,
  source,
  counts,
  keys,
  error,
  total,
}: {
  label: string
  source: string
  counts: Record<string, number>
  keys: readonly string[]
  error: string | null
  total: number
}) {
  return (
    <div className="dash-count-row">
      <div className="dash-count-label">
        <Link to={`/docs/reports/${source}`}>{label}</Link>
        <span className="section-note">전체 {total}건</span>
      </div>
      {error ? <p className="warn">{error}</p> : null}
      <div className="count-tiles dash-count-tiles">
        {keys.map((key) => (
          <Link
            key={key}
            to={`/docs/reports/${source}?status=${key}`}
            className={`count-tile status-${key}`}
          >
            <span className="count-label">{STATUS_LABEL[key] || key}</span>
            <span className="count-value">{counts[key] ?? 0}</span>
          </Link>
        ))}
      </div>
    </div>
  )
}
