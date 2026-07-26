import { Link } from 'react-router-dom'
import { useSessionStatus } from '../../hooks/useSessionStatus'
import { CRAWL_CLASS, formatProgress, formatTime } from '../../lib/format'
import { crawlModeTypeLabel } from '../../lib/collectNav'

export function FnGuideDownloadPage() {
  const { crawl, stale, fetchError, requestingStop, requestLogout } =
    useSessionStatus()
  const busy =
    crawl.state === 'starting' ||
    crawl.state === 'active' ||
    crawl.state === 'stopping'
  const badgeState = fetchError
    ? 'offline'
    : stale
      ? 'stale'
      : CRAWL_CLASS[crawl.state]
  const progress = crawl.progress ?? crawl.crawl?.progress ?? {}
  const typeLabel = crawlModeTypeLabel(crawl.crawl?.mode)

  async function onStop() {
    if (!window.confirm('크롤을 종료하고 로그아웃할까요?')) return
    try {
      await requestLogout()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '종료 요청 실패')
    }
  }

  return (
    <section className={`panel badge-panel state-${badgeState}`}>
      <p className="badge-label">본문 채우기 · 다운로드</p>
      <p className="badge-value">
        {fetchError
          ? 'API Offline'
          : stale
            ? '응답 없음'
            : `FnGuide · ${typeLabel} · ${crawl.label}`}
      </p>
      <p className="account-line">
        지금은 검색 실행 작업이 PDF 다운로드(본문 채우기)까지 같이 돌립니다.
        작업 분리는 아직 없습니다.
      </p>
      {crawl.crawl?.started_at && !fetchError ? (
        <p className="account-line">
          시작 {formatTime(crawl.crawl.started_at)}
          {crawl.crawl.ended_at
            ? ` · 종료 ${formatTime(crawl.crawl.ended_at)}`
            : ''}
        </p>
      ) : null}
      {!fetchError && busy ? (
        <p className="account-line">{formatProgress(progress)}</p>
      ) : null}
      <p className="account-line">
        시작/리스트 발굴 타입:{' '}
        <Link to="/collect/fnguide/list/search">검색 실행</Link>
        {' · '}
        <Link to="/collect/fnguide/list/search/types">리스트 발굴 타입</Link>
        {' · '}
        문서: <Link to="/docs/reports/fnguide">FnGuide 보고서</Link>
      </p>
      {busy ? (
        <div className="actions">
          <button
            type="button"
            disabled={requestingStop || !!fetchError}
            onClick={() => void onStop()}
          >
            {requestingStop ? '요청 중…' : '종료'}
          </button>
        </div>
      ) : null}
    </section>
  )
}
