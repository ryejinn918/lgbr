import { useState } from 'react'
import { useSessionStatus } from './hooks/useSessionStatus'
import type { CrawlMode, CrawlState, SessionRecord, SessionState } from './types'
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
  const [reportLimit, setReportLimit] = useState(5)

  const crawlBusy =
    crawl.state === 'starting' ||
    crawl.state === 'active' ||
    crawl.state === 'stopping'
  const sessionOpen = status.session != null
  const blockedByError = crawl.state === 'error'
  const canStart = crawl.can_start === true && !crawlBusy
  const canStop = crawlBusy || sessionOpen
  const badgeState = fetchError
    ? 'offline'
    : stale
      ? 'stale'
      : CRAWL_CLASS[crawl.state]

  async function onStart(mode: CrawlMode = 'datacenter') {
    const limit = Math.min(50, Math.max(1, Number(reportLimit) || 5))
    const label =
      mode === 'adhoc'
        ? '애드혹 크롤을 시작할까요? (CDP 원격 조작, 로그인 세션 획득)'
        : `데이터센터 리포트 ${limit}건을 다운로드할까요?`
    if (!window.confirm(label)) {
      return
    }
    try {
      await startCrawl(mode, limit)
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
        {crawl.crawl?.mode && !fetchError ? (
          <p className="account-line">
            모드: {crawl.crawl.mode}
            {crawl.crawl.mode === 'datacenter' && crawl.crawl.report_limit
              ? ` · limit ${crawl.crawl.report_limit}`
              : ''}
            {crawl.crawl.cdp_port
              ? ` · CDP ${crawl.crawl.cdp_port}`
              : crawl.crawl.mode === 'adhoc'
                ? ' · CDP 대기'
                : ''}
          </p>
        ) : null}
        {crawl.crawl?.message && !fetchError ? (
          <p className="account-line">메시지: {crawl.crawl.message}</p>
        ) : null}
        {crawl.crawl?.cdp_http_url && !fetchError ? (
          <p className="account-line">CDP: {crawl.crawl.cdp_http_url}</p>
        ) : null}
        {crawl.state === 'active' && !fetchError ? (
          <p className="warn">
            크롤이 계정을 사용 중입니다. 같은 계정으로 들어가면 세션이 끊길 수
            있습니다.
          </p>
        ) : null}
        {blockedByError && !fetchError ? (
          <div className="warn">
            <p>
              오류로 멈췄습니다
              {crawl.crawl?.message ? `: ${crawl.crawl.message}` : '.'} 원인을
              점검한 뒤, 아래 DB에 접속해{' '}
              <code>fnguide_crawls.state</code>를{' '}
              <code>error</code> → <code>ended</code>로 바꾸세요.
            </p>
            {crawl.unblock_text ? (
              <pre className="unblock-sql">{crawl.unblock_text}</pre>
            ) : null}
          </div>
        ) : null}
        {!canStart && !crawlBusy && !blockedByError && !fetchError ? (
          <p className="warn">열린 세션이 남아 있어 실행할 수 없습니다.</p>
        ) : null}
        {stale && !fetchError ? (
          <p className="warn">최근 활동 갱신이 없습니다.</p>
        ) : null}
        {fetchError ? <p className="warn">API 연결 실패: {fetchError}</p> : null}

        <div className="actions">
          <label className="limit-field">
            <span>보고서 수</span>
            <input
              type="number"
              min={1}
              max={50}
              value={reportLimit}
              disabled={!canStart || requestingStart || !!fetchError}
              onChange={(e) => setReportLimit(Number(e.target.value))}
            />
          </label>
          <button
            type="button"
            className="run-btn"
            disabled={!canStart || requestingStart || !!fetchError}
            onClick={() => void onStart('datacenter')}
          >
            {requestingStart ? '시작 중…' : '데이터센터'}
          </button>
          <button
            type="button"
            className="run-btn"
            disabled={!canStart || requestingStart || !!fetchError}
            onClick={() => void onStart('adhoc')}
          >
            {requestingStart ? '시작 중…' : '애드혹'}
          </button>
          <button
            type="button"
            className="logout-btn"
            disabled={!canStop || requestingStop || !!fetchError}
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
