import { Link } from 'react-router-dom'
import { useCollectionJob } from '../../hooks/useCollectionJob'
import { CRAWL_CLASS, formatTime } from '../../lib/format'

/** Same search job as list/search — no separate download stage. */
export function PwcDownloadPage() {
  const collection = useCollectionJob({ source: 'pwc', capability: 'search' })
  const job = collection.status
  const busy =
    job.state === 'starting' ||
    job.state === 'active' ||
    job.state === 'stopping'
  const badgeState = collection.fetchError
    ? 'offline'
    : CRAWL_CLASS[job.state] ?? 'ended'
  const progress = (job.progress ?? job.job?.progress ?? {}) as Record<
    string,
    unknown
  >

  async function onStop() {
    if (!window.confirm('PwC 검색/다운로드 작업을 중단할까요?')) return
    try {
      await collection.stopFeed()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '중단 실패')
    }
  }

  const bits: string[] = []
  if (progress.listed != null) bits.push(`listed ${String(progress.listed)}`)
  if (progress.downloaded != null)
    bits.push(`downloaded ${String(progress.downloaded)}`)
  if (progress.skipped_no_download != null)
    bits.push(`no_pdf ${String(progress.skipped_no_download)}`)

  return (
    <section className={`panel badge-panel state-${badgeState}`}>
      <p className="badge-label">본문 채우기 · 다운로드</p>
      <p className="badge-value">
        {collection.fetchError
          ? 'API Offline'
          : `PwC · 검색 · ${job.label}`}
      </p>
      <p className="account-line">
        검색 실행 작업이 PDF 다운로드까지 같이 돌립니다. 작업 분리는 없습니다.
      </p>
      {job.job?.started_at && !collection.fetchError ? (
        <p className="account-line">
          시작 {formatTime(job.job.started_at)}
          {job.job.ended_at ? ` · 종료 ${formatTime(job.job.ended_at)}` : ''}
          {job.job.message ? ` · ${job.job.message}` : ''}
        </p>
      ) : null}
      {bits.length ? (
        <p className="account-line">{bits.join(' · ')}</p>
      ) : null}
      <p className="account-line">
        시작:{' '}
        <Link to="/collect/pwc/list/search">검색 실행</Link>
        {' · '}
        문서: <Link to="/docs/reports/pwc">PwC 보고서</Link>
      </p>
      {busy ? (
        <div className="button-row">
          <button
            type="button"
            disabled={collection.requestingStop}
            onClick={() => void onStop()}
          >
            {collection.requestingStop ? '중단 중…' : '중단'}
          </button>
        </div>
      ) : null}
    </section>
  )
}
