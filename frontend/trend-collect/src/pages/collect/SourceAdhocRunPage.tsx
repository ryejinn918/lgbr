import { Link, useOutletContext } from 'react-router-dom'
import { useSessionStatus } from '../../hooks/useSessionStatus'
import { CRAWL_CLASS, formatProgress, formatTime } from '../../lib/format'
import { defaultCollectPath, type CollectSource } from '../../lib/collectNav'
import { MEDIA_SOURCES, getMediaSource } from '../../lib/mediaSources'
import type { CrawlMode } from '../../types'

type Ctx = {
  source: CollectSource
}

/** Generic CDP adhoc hold for media sources without a search job yet. */
export function SourceAdhocRunPage() {
  const { source } = useOutletContext<Ctx>()
  const meta = getMediaSource(source)
  const session = useSessionStatus()
  const crawl = session.crawl
  const crawlBusy =
    crawl.state === 'starting' ||
    crawl.state === 'active' ||
    crawl.state === 'stopping'
  const canStart = crawl.can_start === true && !crawlBusy
  const isThisSource = crawl.crawl?.mode === source
  const badgeState = session.fetchError
    ? 'offline'
    : CRAWL_CLASS[crawl.state] ?? 'ended'
  const progress = crawl.progress ?? crawl.crawl?.progress ?? {}
  const cdpPort = crawl.crawl?.cdp_port
  const label = meta?.label ?? source
  const hubUrl = meta?.hubUrl ?? ''
  const badgeValue = session.fetchError
    ? 'API Offline'
    : isThisSource
      ? `${label} · 애드혹 · ${crawl.label}`
      : crawlBusy
        ? `${label} · 대기 (다른 세션이 브라우저 사용 중)`
        : `${label} · 유휴`

  async function onStart() {
    if (!window.confirm(`${label} 애드혹을 시작할까요?\n${hubUrl}`)) {
      return
    }
    try {
      await session.startCrawl(source as CrawlMode)
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '실행 실패')
    }
  }

  async function onStop() {
    if (!window.confirm(`${label} 애드혹 브라우저를 종료할까요?`)) return
    try {
      await session.requestLogout()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '종료 요청 실패')
    }
  }

  if (!meta) {
    return (
      <section className="panel">
        <p className="warn">알 수 없는 매체: {source}</p>
      </section>
    )
  }

  return (
    <section className={`panel badge-panel state-${badgeState}`}>
      <p className="badge-label">애드혹 · 실행</p>
      <p className="badge-value">{badgeValue}</p>
      <p className="account-line">
        허브를 Chrome+CDP로 엽니다. 목록/PDF 자동 수집은 아직 없습니다. 허브:{' '}
        <a href={hubUrl} target="_blank" rel="noreferrer">
          {hubUrl.replace(/^https?:\/\//, '')}
        </a>
      </p>

      {crawl.crawl?.started_at && !session.fetchError ? (
        <p className="account-line">
          시작 {formatTime(crawl.crawl.started_at)}
          {crawl.crawl.ended_at
            ? ` · 종료 ${formatTime(crawl.crawl.ended_at)}`
            : ''}
        </p>
      ) : null}

      {isThisSource && cdpPort && !session.fetchError ? (
        <p className="account-line">
          CDP <code>http://127.0.0.1:{String(cdpPort)}</code>
          {typeof progress.url === 'string' ? ` · ${progress.url}` : ''}
        </p>
      ) : null}
      {!session.fetchError && crawlBusy ? (
        <p className="account-line">{formatProgress(progress)}</p>
      ) : null}

      <p className="account-line">
        다른 매체:{' '}
        <Link to={defaultCollectPath('fnguide')}>FnGuide</Link>
        {MEDIA_SOURCES.filter((s) => s.id !== source).map((s) => (
          <span key={s.id}>
            {' · '}
            <Link to={defaultCollectPath(s.id as CollectSource)}>{s.label}</Link>
          </span>
        ))}
      </p>

      <div className="actions">
        <button
          type="button"
          disabled={!canStart || session.requestingStart}
          onClick={() => void onStart()}
        >
          {session.requestingStart ? '시작 중…' : '애드혹 시작'}
        </button>
        <button
          type="button"
          disabled={(!crawlBusy && !isThisSource) || session.requestingStop}
          onClick={() => void onStop()}
        >
          {session.requestingStop ? '종료 중…' : '애드혹 종료'}
        </button>
      </div>
    </section>
  )
}
