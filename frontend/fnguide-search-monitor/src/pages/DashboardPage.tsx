import { Link } from 'react-router-dom'
import { useSessionStatus } from '../hooks/useSessionStatus'
import { useReports } from '../hooks/useReports'
import {
  CRAWL_CLASS,
  STATUS_LABEL,
  formatProgress,
  formatPublishedAt,
  formatRelative,
  latestReportTitle,
} from '../lib/format'

const COUNT_KEYS = [
  'downloaded',
  'blind',
  'listed',
  'no_download',
  'failed',
] as const

export function DashboardPage() {
  const { crawl, status, stale, fetchError, requestingStop, requestLogout } =
    useSessionStatus()
  const crawlBusy =
    crawl.state === 'starting' ||
    crawl.state === 'active' ||
    crawl.state === 'stopping'
  // /api/crawl returns the latest row even when ended; only bind open crawls.
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
    limit: 15,
    offset: 0,
    poll: true,
  })
  const pipeline = useReports({
    limit: 1,
    offset: 0,
    poll: true,
  })

  const badgeState = fetchError
    ? 'offline'
    : stale
      ? 'stale'
      : CRAWL_CLASS[crawl.state]

  async function onStop() {
    if (!window.confirm('크롤을 종료하고 로그아웃할까요?')) return
    try {
      await requestLogout()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '종료 요청 실패')
    }
  }

  return (
    <>
      <header className="monitor-header">
        <h1>운영 대시보드</h1>
        <p className="lede">지금 도는 크롤과 수집 중인 보고서입니다.</p>
      </header>

      <section className={`panel live-strip state-${badgeState}`}>
        <div className="live-main">
          <p className="badge-label">라이브</p>
          <p className="badge-value live-value">
            {fetchError
              ? 'API Offline'
              : stale
                ? '응답 없음'
                : crawlBusy
                  ? crawl.label
                  : '유휴'}
          </p>
          {!fetchError && crawlBusy && crawl.crawl ? (
            <p className="live-meta">
              {[
                crawl.crawl.mode,
                crawl.crawl.report_limit != null
                  ? `limit ${crawl.crawl.report_limit}`
                  : null,
                crawl.crawl.asset_id,
                progress.keyword != null ? `kw=${String(progress.keyword)}` : null,
                crawl.crawl.debug ? 'debug' : null,
                crawl.crawl.cdp_port ? `CDP ${crawl.crawl.cdp_port}` : null,
                formatProgress(progress),
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
          ) : null}
          {!fetchError && crawlBusy && currentRpt ? (
            <p className="live-current">
              현재{' '}
              <span className="mono">{currentRpt}</span>
              {currentTitle ? ` · ${currentTitle}` : ''}
            </p>
          ) : null}
          {!fetchError && !crawlBusy ? (
            <p className="live-meta">
              계정: {status.label}
              {' · '}
              <Link to="/crawl">크롤에서 시작</Link>
            </p>
          ) : null}
          {fetchError ? (
            <p className="warn">API 연결 실패: {fetchError}</p>
          ) : null}
        </div>
        {crawlBusy ? (
          <button
            type="button"
            className="logout-btn"
            disabled={requestingStop || !!fetchError}
            onClick={() => void onStop()}
          >
            {requestingStop ? '요청 중…' : '종료'}
          </button>
        ) : null}
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>이번 수집</h2>
          {openId ? (
            <span className="section-note">{activeReports.total}건</span>
          ) : null}
        </div>
        {!openId ? (
          <p className="empty">진행 중인 수집 없음</p>
        ) : activeReports.error ? (
          <p className="warn">{activeReports.error}</p>
        ) : activeReports.loading && activeReports.items.length === 0 ? (
          <p className="empty">불러오는 중…</p>
        ) : activeReports.items.length === 0 ? (
          <p className="empty">아직 리스트에 기록된 보고서가 없습니다.</p>
        ) : (
          <div className="report-sheet">
            <table className="report-table">
              <thead>
                <tr>
                  <th>상태</th>
                  <th>제목</th>
                  <th>증권사</th>
                  <th>발행일</th>
                  <th>rpt_id</th>
                  <th>파일</th>
                  <th>최근</th>
                </tr>
              </thead>
              <tbody>
                {activeReports.items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <span className={`status-pill status-${item.status}`}>
                        {STATUS_LABEL[item.status] || item.status}
                      </span>
                    </td>
                    <td className="report-title">{item.title}</td>
                    <td>{item.provider || '—'}</td>
                    <td className="mono">
                      {formatPublishedAt(item.published_at)}
                    </td>
                    <td className="mono">{item.source_key}</td>
                    <td className="report-file">
                      {item.has_file ? (
                        <a
                          className="report-file-link"
                          href={`/api/reports/${item.id}/file`}
                          download={item.file_name || undefined}
                          title={item.file_name || '다운로드'}
                        >
                          {item.file_name || '파일'}
                        </a>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>{formatRelative(item.last_seen_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>파이프라인</h2>
          <span className="section-note">
            전체 {pipeline.counts.all ?? 0}건
          </span>
        </div>
        {pipeline.error ? <p className="warn">{pipeline.error}</p> : null}
        <div className="count-tiles">
          {COUNT_KEYS.map((key) => (
            <Link
              key={key}
              to={`/reports?status=${key}`}
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
