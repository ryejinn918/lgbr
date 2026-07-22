import { useSessionStatus } from './hooks/useSessionStatus'
import type { CrawlState, SessionRecord, SessionState } from './types'
import './App.css'

const CRAWL_CLASS: Record<CrawlState, string> = {
  starting: 'starting',
  active: 'active',
  stopping: 'stopping',
  ended: 'ended',
  error: 'error',
}

const SESSION_CLASS: Record<SessionState, string> = {
  logging_in: 'logging_in',
  logged_in: 'logged_in',
  logging_out: 'logging_out',
  ended: 'ended',
  error: 'error',
}

function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const ms = Date.parse(value)
  if (Number.isNaN(ms)) return value
  return new Date(ms).toLocaleString()
}

function App() {
  const {
    crawl,
    status,
    history,
    stale,
    fetchError,
    requestingStart,
    requestingStop,
    startCrawl,
    requestLogout,
  } = useSessionStatus()

  const crawlBusy =
    crawl.state === 'starting' ||
    crawl.state === 'active' ||
    crawl.state === 'stopping'
  const canStart = crawl.can_start !== false && !crawlBusy
  const badgeState = fetchError
    ? 'offline'
    : stale
      ? 'stale'
      : CRAWL_CLASS[crawl.state]

  async function onStart() {
    if (!window.confirm('크롤을 시작할까요? (로그인 세션을 함께 획득합니다)')) {
      return
    }
    try {
      await startCrawl()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '실행 실패')
    }
  }

  async function onStop() {
    if (!window.confirm('크롤을 종료하고 로그아웃할까요?')) return
    try {
      await requestLogout()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '종료 요청 실패')
    }
  }

  return (
    <main className="monitor">
      <header className="monitor-header">
        <p className="brand">fnguide-search-monitor</p>
        <h1>크롤 상태</h1>
        <p className="lede">수동 크롤 실행과 Fnguide 계정 사용 여부입니다.</p>
      </header>

      <section className={`panel badge-panel state-${badgeState}`}>
        <p className="badge-label">크롤</p>
        <p className="badge-value">
          {fetchError ? 'API Offline' : stale ? '응답 없음' : crawl.label}
        </p>
        <p className={`account-line state-${SESSION_CLASS[status.state]}`}>
          계정: {fetchError ? '—' : status.label}
        </p>
        {crawl.state === 'active' && !fetchError ? (
          <p className="warn">
            크롤이 계정을 사용 중입니다. 같은 계정으로 들어가면 세션이 끊길 수
            있습니다.
          </p>
        ) : null}
        {crawl.state === 'error' &&
        crawl.crawl &&
        !crawl.crawl.ended_at &&
        !fetchError ? (
          <p className="warn">
            오류 상태입니다
            {crawl.crawl.message ? `: ${crawl.crawl.message}` : '.'} 원인 확인 후
            다시 실행하세요.
          </p>
        ) : null}
        {!canStart && !crawlBusy && !fetchError && crawl.state !== 'error' ? (
          <p className="warn">열린 세션이 남아 있어 실행할 수 없습니다.</p>
        ) : null}
        {stale && !fetchError ? (
          <p className="warn">최근 활동 갱신이 없습니다.</p>
        ) : null}
        {fetchError ? <p className="warn">API 연결 실패: {fetchError}</p> : null}

        <div className="actions">
          <button
            type="button"
            className="run-btn"
            disabled={!canStart || requestingStart || !!fetchError}
            onClick={() => void onStart()}
          >
            {requestingStart ? '시작 중…' : '실행'}
          </button>
          <button
            type="button"
            className="logout-btn"
            disabled={!crawlBusy || requestingStop || !!fetchError}
            onClick={() => void onStop()}
          >
            {requestingStop ? '요청 중…' : '종료'}
          </button>
        </div>
      </section>

      <section className="panel details">
        <dl>
          <div>
            <dt>계정</dt>
            <dd>{status.session?.fnguide_user_id ?? '—'}</dd>
          </div>
          <div>
            <dt>시작</dt>
            <dd>
              {formatTime(crawl.crawl?.started_at ?? status.session?.started_at)}
            </dd>
          </div>
          <div>
            <dt>최근 사용</dt>
            <dd>{formatTime(status.session?.last_used_at)}</dd>
          </div>
        </dl>
      </section>

      <section className="panel history">
        <h2>로그인 이력</h2>
        {history.length === 0 ? (
          <p className="empty">이력이 없습니다.</p>
        ) : (
          <ul>
            {history.map((item: SessionRecord) => (
              <li key={item.id}>
                <div className="history-main">
                  <span className="history-label">{item.label}</span>
                  <span className="history-user">{item.fnguide_user_id}</span>
                </div>
                <div className="history-meta">
                  {formatTime(item.started_at)} ~ {formatTime(item.ended_at)}
                  {item.end_reason_label ? ` · ${item.end_reason_label}` : ''}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}

export default App
