import { useSessionStatus } from './hooks/useSessionStatus'
import type { SessionRecord, SessionState } from './types'
import './App.css'

const STATE_CLASS: Record<SessionState, string> = {
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
    status,
    history,
    stale,
    fetchError,
    requestingLogout,
    requestLogout,
  } = useSessionStatus()

  const busy =
    status.state === 'logged_in' ||
    status.state === 'logging_in' ||
    status.state === 'logging_out'
  const badgeState = fetchError
    ? 'offline'
    : stale
      ? 'stale'
      : STATE_CLASS[status.state]

  async function onLogout() {
    if (!window.confirm('Fnguide 계정에서 로그아웃할까요?')) return
    try {
      await requestLogout()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '로그아웃 요청 실패')
    }
  }

  return (
    <main className="monitor">
      <header className="monitor-header">
        <p className="brand">fnguide-search-monitor</p>
        <h1>계정 상태</h1>
        <p className="lede">봇의 Fnguide 계정 사용 여부와 로그인 이력을 봅니다.</p>
      </header>

      <section className={`panel badge-panel state-${badgeState}`}>
        <p className="badge-label">상태</p>
        <p className="badge-value">
          {fetchError ? 'API Offline' : stale ? '응답 없음' : status.label}
        </p>
        {status.state === 'logged_in' && !fetchError ? (
          <p className="warn">
            계정을 사용 중입니다. 같은 계정으로 들어가면 봇 세션이 끊길 수
            있습니다.
          </p>
        ) : null}
        {stale && !fetchError ? (
          <p className="warn">최근 활동 갱신이 없습니다.</p>
        ) : null}
        {fetchError ? <p className="warn">API 연결 실패: {fetchError}</p> : null}

        <div className="actions">
          <button
            type="button"
            className="logout-btn"
            disabled={!busy || requestingLogout || !!fetchError}
            onClick={() => void onLogout()}
          >
            {requestingLogout ? '요청 중…' : '로그아웃'}
          </button>
        </div>
      </section>

      <section className="panel details">
        <dl>
          <div>
            <dt>user_id</dt>
            <dd>{status.session?.fnguide_user_id ?? '—'}</dd>
          </div>
          <div>
            <dt>pid</dt>
            <dd>{status.session?.pid ?? '—'}</dd>
          </div>
          <div>
            <dt>started_at</dt>
            <dd>{formatTime(status.session?.started_at)}</dd>
          </div>
          <div>
            <dt>last_used_at</dt>
            <dd>{formatTime(status.session?.last_used_at)}</dd>
          </div>
          <div>
            <dt>lease_until</dt>
            <dd>{formatTime(status.session?.lease_until)}</dd>
          </div>
          <div>
            <dt>logout_requested_at</dt>
            <dd>{formatTime(status.session?.logout_requested_at)}</dd>
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
