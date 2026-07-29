import { Link } from 'react-router-dom'
import { CoverageGrass } from '../components/CoverageGrass'
import { useCollectionJob } from '../hooks/useCollectionJob'
import { useCoverage } from '../hooks/useCoverage'
import { useReports } from '../hooks/useReports'
import { useSessionStatus } from '../hooks/useSessionStatus'
import {
  CRAWL_CLASS,
  STATUS_LABEL,
  formatProgress,
  formatPublishedAt,
  formatTime,
} from '../lib/format'
import { crawlModeTypeLabel, isFnguideCrawlMode } from '../lib/collectNav'
import type { CollectionJobRecord, CollectionJobResponse } from '../types'

const SOURCE_LABEL: Record<string, string> = {
  fnguide: 'FnGuide',
  pwc: 'PwC',
  accenture: 'Accenture',
  kpmg: 'KPMG',
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

function argBadgeLabel(kind: 'feed' | 'fetch_body') {
  return kind === 'fetch_body'
    ? 'ARG · 본문 채우기'
    : 'ARG · 피드'
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

  const crawlMode = crawl.crawl?.mode ?? null
  const fnguideOwned =
    isBusy(crawl.state) && isFnguideCrawlMode(crawlMode)
  const pwcAdhoc =
    isBusy(crawl.state) && crawlMode === 'pwc'
  const accentureAdhoc =
    isBusy(crawl.state) && crawlMode === 'accenture'
  const kpmgAdhoc =
    isBusy(crawl.state) && crawlMode === 'kpmg'

  const argView = pickArgView(argFeed.status, argBody.status)
  const argActive = argView.kind === 'fetch_body' ? argBody : argFeed
  const argBusy = isBusy(argView.status.state)
  const pwcSearchBusy = isBusy(pwcSearch.status.state)
  const accentureSearchBusy = isBusy(accentureSearch.status.state)
  const kpmgSearchBusy = isBusy(kpmgSearch.status.state)
  const pwcBusy = pwcSearchBusy || pwcAdhoc
  const accentureBusy = accentureSearchBusy || accentureAdhoc
  const kpmgBusy = kpmgSearchBusy || kpmgAdhoc

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
  const argProgress = (argView.status.progress ??
    argView.status.job?.progress ??
    {}) as Record<string, unknown>

  const coverage = useCoverage(13)
  const recent = useReports({
    limit: 4,
    offset: 0,
    poll: true,
  })
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
    source: 'pwc' | 'accenture' | 'kpmg',
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
            FnGuide · ARG · PwC · Accenture · KPMG
          </span>
        </div>
        <div className="job-board">
          <article className={`job-card state-${fnguideBadge}`}>
            <p className="badge-label">
              FnGuide · 검색
              {fnguideOwned
                ? ` · ${crawlModeTypeLabel(crawlMode)}`
                : ''}
            </p>
            <p className="badge-value">{fnguideValue}</p>
            <p className="account-line">
              계정 {fetchError ? '—' : status.label}
              {fnguideOwned && crawl.crawl?.started_at
                ? ` · ${formatTime(crawl.crawl.started_at)}`
                : ''}
            </p>
            {fnguideOwned ? (
              <p className="account-line">
                {[
                  crawl.crawl?.asset_id,
                  crawlProgress.keyword != null
                    ? `kw=${String(crawlProgress.keyword)}`
                    : null,
                  formatProgress(crawlProgress),
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            ) : null}
            <p className="account-line">
              <Link to="/collect/fnguide/list/search">검색 실행</Link>
              {' · '}
              <Link to="/docs/reports/fnguide">보고서</Link>
            </p>
            {fnguideOwned ? (
              <div className="actions">
                <button
                  type="button"
                  disabled={requestingStop || !!fetchError}
                  onClick={() => void onStopFnguide()}
                >
                  {requestingStop ? '요청 중…' : '종료'}
                </button>
              </div>
            ) : null}
          </article>

          <article className={`job-card state-${argBadge}`}>
            <p className="badge-label">{argBadgeLabel(argView.kind)}</p>
            <p className="badge-value">
              {argOffline
                ? 'API Offline'
                : argBusy
                  ? argView.status.label
                  : argView.status.job
                    ? argView.status.label
                    : '유휴'}
            </p>
            {argView.status.job?.started_at ? (
              <p className="account-line">
                {formatTime(argView.status.job.started_at)}
                {argView.status.job.ended_at
                  ? ` · ${formatTime(argView.status.job.ended_at)}`
                  : ''}
              </p>
            ) : null}
            {argBusy || argView.status.job?.message ? (
              <p className="account-line">
                {formatArgProgress(
                  argView.kind,
                  argView.status.job,
                  argProgress,
                )}
              </p>
            ) : null}
            <p className="account-line">
              <Link to="/collect/arg/list/feed">피드</Link>
              {' · '}
              <Link to="/collect/arg/body/fetch">본문</Link>
              {' · '}
              <Link to="/docs/articles">기사</Link>
            </p>
            {argBusy ? (
              <div className="actions">
                <button
                  type="button"
                  disabled={argActive.requestingStop}
                  onClick={() => void onStopArg()}
                >
                  {argActive.requestingStop ? '요청 중…' : '중단'}
                </button>
              </div>
            ) : null}
          </article>

          <article className={`job-card state-${pwcBadge}`}>
            <p className="badge-label">
              PwC · 검색
              {pwcAdhoc ? ' · 애드혹' : ''}
            </p>
            <p className="badge-value">{pwcValue}</p>
            {pwcSearchBusy && pwcSearch.status.job?.started_at ? (
              <p className="account-line">
                {formatTime(pwcSearch.status.job.started_at)}
                {pwcSearch.status.job.ended_at
                  ? ` · ${formatTime(pwcSearch.status.job.ended_at)}`
                  : ''}
              </p>
            ) : null}
            {pwcAdhoc && crawl.crawl?.started_at ? (
              <p className="account-line">
                애드혹 {formatTime(crawl.crawl.started_at)}
                {crawl.crawl.cdp_port
                  ? ` · CDP ${crawl.crawl.cdp_port}`
                  : ''}
              </p>
            ) : null}
            {pwcSearchBusy ? (
              <p className="account-line">
                {formatSearchProgress(pwcProgress) ||
                  pwcSearch.status.job?.message ||
                  '—'}
              </p>
            ) : null}
            {pwcAdhoc && !pwcSearchBusy ? (
              <p className="account-line">
                {typeof crawlProgress.url === 'string'
                  ? crawlProgress.url
                  : formatProgress(crawlProgress)}
              </p>
            ) : null}
            <p className="account-line">
              <Link to="/collect/pwc/list/search">검색 실행</Link>
              {' · '}
              <Link to="/docs/reports/pwc">보고서</Link>
            </p>
            {pwcBusy ? (
              <div className="actions">
                <button
                  type="button"
                  disabled={
                    pwcSearchBusy
                      ? pwcSearch.requestingStop
                      : requestingStop || !!fetchError
                  }
                  onClick={() =>
                    void onStopMedia(
                      'pwc',
                      pwcSearchBusy,
                      pwcAdhoc,
                      () => pwcSearch.stopFeed(),
                    )
                  }
                >
                  {(pwcSearchBusy
                    ? pwcSearch.requestingStop
                    : requestingStop)
                    ? '요청 중…'
                    : pwcSearchBusy
                      ? '검색 중단'
                      : '애드혹 종료'}
                </button>
              </div>
            ) : null}
          </article>

          <article className={`job-card state-${accentureBadge}`}>
            <p className="badge-label">
              Accenture · 검색
              {accentureAdhoc ? ' · 애드혹' : ''}
            </p>
            <p className="badge-value">{accentureValue}</p>
            {accentureSearchBusy && accentureSearch.status.job?.started_at ? (
              <p className="account-line">
                {formatTime(accentureSearch.status.job.started_at)}
                {accentureSearch.status.job.ended_at
                  ? ` · ${formatTime(accentureSearch.status.job.ended_at)}`
                  : ''}
              </p>
            ) : null}
            {accentureAdhoc && crawl.crawl?.started_at ? (
              <p className="account-line">
                애드혹 {formatTime(crawl.crawl.started_at)}
                {crawl.crawl.cdp_port
                  ? ` · CDP ${crawl.crawl.cdp_port}`
                  : ''}
              </p>
            ) : null}
            {accentureSearchBusy ? (
              <p className="account-line">
                {formatSearchProgress(accentureProgress) ||
                  accentureSearch.status.job?.message ||
                  '—'}
              </p>
            ) : null}
            {accentureAdhoc && !accentureSearchBusy ? (
              <p className="account-line">
                {typeof crawlProgress.url === 'string'
                  ? crawlProgress.url
                  : formatProgress(crawlProgress)}
              </p>
            ) : null}
            <p className="account-line">
              <Link to="/collect/accenture/list/search">검색 실행</Link>
              {' · '}
              <Link to="/docs/reports/accenture">보고서</Link>
            </p>
            {accentureBusy ? (
              <div className="actions">
                <button
                  type="button"
                  disabled={
                    accentureSearchBusy
                      ? accentureSearch.requestingStop
                      : requestingStop || !!fetchError
                  }
                  onClick={() =>
                    void onStopMedia(
                      'accenture',
                      accentureSearchBusy,
                      accentureAdhoc,
                      () => accentureSearch.stopFeed(),
                    )
                  }
                >
                  {(accentureSearchBusy
                    ? accentureSearch.requestingStop
                    : requestingStop)
                    ? '요청 중…'
                    : accentureSearchBusy
                      ? '검색 중단'
                      : '애드혹 종료'}
                </button>
              </div>
            ) : null}
          </article>

          <article className={`job-card state-${kpmgBadge}`}>
            <p className="badge-label">
              KPMG · 검색
              {kpmgAdhoc ? ' · 애드혹' : ''}
            </p>
            <p className="badge-value">{kpmgValue}</p>
            {kpmgSearchBusy && kpmgSearch.status.job?.started_at ? (
              <p className="account-line">
                {formatTime(kpmgSearch.status.job.started_at)}
                {kpmgSearch.status.job.ended_at
                  ? ` · ${formatTime(kpmgSearch.status.job.ended_at)}`
                  : ''}
              </p>
            ) : null}
            {kpmgAdhoc && crawl.crawl?.started_at ? (
              <p className="account-line">
                {formatTime(crawl.crawl.started_at)}
                {crawl.crawl.cdp_port
                  ? ` · CDP ${crawl.crawl.cdp_port}`
                  : ''}
              </p>
            ) : null}
            {kpmgSearchBusy ? (
              <p className="account-line">
                {formatSearchProgress(kpmgProgress) ||
                  kpmgSearch.status.job?.message ||
                  '…'}
              </p>
            ) : null}
            {kpmgAdhoc && !kpmgSearchBusy ? (
              <p className="account-line">
                {typeof crawlProgress.url === 'string'
                  ? crawlProgress.url
                  : formatProgress(crawlProgress)}
              </p>
            ) : null}
            <p className="account-line">
              <Link to="/collect/kpmg/list/search">검색 실행</Link>
              {' · '}
              <Link to="/docs/reports/kpmg">보고서</Link>
            </p>
            {kpmgBusy ? (
              <div className="actions">
                <button
                  type="button"
                  disabled={
                    kpmgSearchBusy
                      ? kpmgSearch.requestingStop
                      : requestingStop || !!fetchError
                  }
                  onClick={() =>
                    void onStopMedia(
                      'kpmg',
                      kpmgSearchBusy,
                      kpmgAdhoc,
                      () => kpmgSearch.stopFeed(),
                    )
                  }
                >
                  {(kpmgSearchBusy
                    ? kpmgSearch.requestingStop
                    : requestingStop)
                    ? '요청 중…'
                    : kpmgSearchBusy
                      ? '검색 중단'
                      : '애드혹 종료'}
                </button>
              </div>
            ) : null}
          </article>
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
            최신 4건
          </span>
        </div>
        {recent.error ? (
          <p className="warn">{recent.error}</p>
        ) : recent.items.length === 0 ? (
          <p className="empty">아직 수집된 보고서가 없습니다.</p>
        ) : (
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
                {recent.items.map((item) => (
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
