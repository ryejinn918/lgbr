import { Link } from 'react-router-dom'
import { useCollectionJob } from '../hooks/useCollectionJob'
import { useNewsArticles } from '../hooks/useNewsArticles'
import { useReports } from '../hooks/useReports'
import { useSessionStatus } from '../hooks/useSessionStatus'
import {
  CRAWL_CLASS,
  STATUS_LABEL,
  formatProgress,
  formatPublishedAt,
  formatRelative,
  formatTime,
  latestReportTitle,
} from '../lib/format'
import { crawlModeTypeLabel } from '../lib/collectNav'

const COUNT_KEYS = [
  'downloaded',
  'blind',
  'listed',
  'no_download',
  'failed',
] as const

function isBusy(state: string) {
  return state === 'starting' || state === 'active' || state === 'stopping'
}

export function DashboardPage() {
  const { crawl, status, stale, fetchError, requestingStop, requestLogout } =
    useSessionStatus()
  const argFeed = useCollectionJob({ source: 'arg' })
  const crawlBusy = isBusy(crawl.state)
  const argBusy = isBusy(argFeed.status.state)
  const openId =
    crawlBusy && crawl.crawl?.id && !crawl.crawl.ended_at
      ? crawl.crawl.id
      : null
  const progress = crawl.progress ?? {}
  const currentRpt =
    progress.current_rpt_id != null ? String(progress.current_rpt_id) : null
  const currentTitle = latestReportTitle(crawl.events, currentRpt)

  const activeReports = useReports({
    crawlId: openId,
    limit: 10,
    offset: 0,
    poll: true,
  })
  const pipeline = useReports({
    limit: 1,
    offset: 0,
    poll: true,
  })
  const recentArg = useNewsArticles({
    source: 'arg',
    limit: 8,
    offset: 0,
  })

  const crawlBadge = fetchError
    ? 'offline'
    : stale
      ? 'stale'
      : CRAWL_CLASS[crawl.state]
  const argBadge = argFeed.fetchError
    ? 'offline'
    : CRAWL_CLASS[argFeed.status.state] ?? 'ended'

  async function onStopCrawl() {
    if (!window.confirm('FnGuide 크롤을 종료하고 로그아웃할까요?')) return
    try {
      await requestLogout()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '종료 요청 실패')
    }
  }

  async function onStopArg() {
    if (!window.confirm('ARG 피드 잡을 중단할까요?')) return
    try {
      await argFeed.stopFeed()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '중단 실패')
    }
  }

  const argProgress = (argFeed.status.progress ??
    argFeed.status.job?.progress ??
    {}) as Record<string, unknown>

  return (
    <>
      <header className="monitor-header">
        <h1>운영 대시보드</h1>
        <p className="lede">
          모든 수집 작업을 한곳에서 봅니다. 시작은 각 매체 수집 화면에서 합니다.
        </p>
      </header>

      <section className="panel">
        <div className="section-head">
          <h2>수집 작업</h2>
          <span className="section-note">매체 · 단계 · 수단 · 리스트 발굴 타입</span>
        </div>
        <div className="job-board">
          <article className={`job-card state-${crawlBadge}`}>
            <p className="badge-label">
              FnGuide · 리스트 발굴/검색
              {crawlBusy ? '+다운로드' : ''} ·{' '}
              {crawlModeTypeLabel(crawl.crawl?.mode)}
            </p>
            <p className="badge-value">
              {fetchError
                ? 'API Offline'
                : stale
                  ? '응답 없음'
                  : crawlBusy
                    ? crawl.label
                    : crawl.crawl
                      ? crawl.label
                      : '유휴'}
            </p>
            <p className="account-line">
              계정 {fetchError ? '—' : status.label}
              {crawl.crawl?.started_at
                ? ` · ${formatTime(crawl.crawl.started_at)}`
                : ''}
            </p>
            {crawlBusy && crawl.crawl ? (
              <p className="account-line">
                {[
                  crawl.crawl.asset_id,
                  progress.keyword != null
                    ? `kw=${String(progress.keyword)}`
                    : null,
                  formatProgress(progress),
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            ) : null}
            {crawlBusy && currentRpt ? (
              <p className="account-line">
                현재 <span className="mono">{currentRpt}</span>
                {currentTitle ? ` · ${currentTitle}` : ''}
              </p>
            ) : null}
            <p className="account-line">
              <Link to="/collect/fnguide/list/search">검색 실행</Link>
              {' · '}
              <Link to="/collect/fnguide/list/search/types">리스트 발굴 타입</Link>
              {' · '}
              <Link to="/docs/reports/fnguide">FnGuide 보고서</Link>
            </p>
            {crawlBusy ? (
              <div className="actions">
                <button
                  type="button"
                  disabled={requestingStop || !!fetchError}
                  onClick={() => void onStopCrawl()}
                >
                  {requestingStop ? '요청 중…' : '종료'}
                </button>
              </div>
            ) : null}
          </article>

          <article className={`job-card state-${argBadge}`}>
            <p className="badge-label">ARG · 리스트 발굴/피드 · 전체</p>
            <p className="badge-value">
              {argFeed.fetchError
                ? 'API Offline'
                : argBusy
                  ? argFeed.status.label
                  : argFeed.status.job
                    ? argFeed.status.label
                    : '유휴'}
            </p>
            {argFeed.status.job?.started_at ? (
              <p className="account-line">
                {formatTime(argFeed.status.job.started_at)}
                {argFeed.status.job.ended_at
                  ? ` · ${formatTime(argFeed.status.job.ended_at)}`
                  : ''}
              </p>
            ) : null}
            {argBusy || argFeed.status.job?.message ? (
              <p className="account-line">
                {[
                  argProgress.inserted != null
                    ? `신규 ${String(argProgress.inserted)}`
                    : null,
                  argProgress.page != null
                    ? `page ${String(argProgress.page)}`
                    : null,
                  argFeed.status.job?.message,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
            ) : null}
            <p className="account-line">
              <Link to="/collect/arg/list/feed">피드 실행</Link>
              {' · '}
              <Link to="/collect/arg/list/feed/types">리스트 발굴 타입</Link>
              {' · '}
              <Link to="/docs/articles">기사</Link>
            </p>
            {argBusy ? (
              <div className="actions">
                <button
                  type="button"
                  disabled={argFeed.requestingStop}
                  onClick={() => void onStopArg()}
                >
                  {argFeed.requestingStop ? '요청 중…' : '중단'}
                </button>
              </div>
            ) : null}
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>FnGuide · 이번 리스트 발굴</h2>
          {openId ? (
            <span className="section-note">{activeReports.total}건</span>
          ) : null}
        </div>
        {!openId ? (
          <p className="empty">진행 중인 FnGuide 검색 작업 없음</p>
        ) : activeReports.error ? (
          <p className="warn">{activeReports.error}</p>
        ) : activeReports.items.length === 0 ? (
          <p className="empty">아직 리스트에 기록된 보고서가 없습니다.</p>
        ) : (
          <div className="report-sheet">
            <table className="report-table">
              <thead>
                <tr>
                  <th className="col-status">상태</th>
                  <th className="col-title">제목</th>
                  <th className="col-provider">증권사</th>
                  <th className="col-published">발행일</th>
                  <th className="col-seen">최근</th>
                </tr>
              </thead>
              <tbody>
                {activeReports.items.map((item) => (
                  <tr key={item.id}>
                    <td className="col-status">
                      <span className={`status-pill status-${item.status}`}>
                        {STATUS_LABEL[item.status] || item.status}
                      </span>
                    </td>
                    <td className="col-title report-title" title={item.title}>
                      {item.title}
                    </td>
                    <td className="col-provider">{item.provider || '—'}</td>
                    <td className="col-published mono">
                      {formatPublishedAt(item.published_at)}
                    </td>
                    <td className="col-seen">
                      {formatRelative(item.last_seen_at)}
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
          <h2>ARG · 최근 리스트</h2>
          <span className="section-note">{recentArg.total}건</span>
        </div>
        {recentArg.fetchError ? (
          <p className="warn">{recentArg.fetchError}</p>
        ) : recentArg.items.length === 0 ? (
          <p className="empty">
            아직 ARG 리스트가 없습니다.{' '}
            <Link to="/collect/arg/list/feed">피드 실행</Link>
          </p>
        ) : (
          <div className="report-sheet">
            <table className="report-table">
              <thead>
                <tr>
                  <th className="col-published">발행</th>
                  <th className="col-provider">섹션</th>
                  <th className="col-title">제목</th>
                </tr>
              </thead>
              <tbody>
                {recentArg.items.map((item) => (
                  <tr key={item.id}>
                    <td className="col-published mono">
                      {formatPublishedAt(item.published_at)}
                    </td>
                    <td className="col-provider">
                      {item.section || item.publisher || '—'}
                    </td>
                    <td className="col-title report-title">
                      <a href={item.url} target="_blank" rel="noreferrer">
                        {item.title}
                      </a>
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
          <h2>FnGuide 파이프라인</h2>
          <span className="section-note">
            전체 {pipeline.counts.all ?? 0}건
          </span>
        </div>
        {pipeline.error ? <p className="warn">{pipeline.error}</p> : null}
        <div className="count-tiles">
          {COUNT_KEYS.map((key) => (
            <Link
              key={key}
              to={`/docs/reports/fnguide?status=${key}`}
              className={`count-tile status-${key}`}
            >
              <span className="count-label">{STATUS_LABEL[key]}</span>
              <span className="count-value">{pipeline.counts[key] ?? 0}</span>
            </Link>
          ))}
        </div>
      </section>
    </>
  )
}
