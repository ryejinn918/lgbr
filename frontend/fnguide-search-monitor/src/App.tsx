import { useSessionStatus } from './hooks/useSessionStatus'
import type { SessionState } from './types'
import './App.css'

const STATE_LABEL: Record<SessionState, string> = {
  idle: 'Idle',
  logging_in: 'Logging in',
  active: 'Active',
  logging_out: 'Logging out',
  error: 'Error',
}

function formatTime(value: string | null): string {
  if (!value) return '—'
  const ms = Date.parse(value)
  if (Number.isNaN(ms)) return value
  return new Date(ms).toLocaleString()
}

function App() {
  const { status, stale, fetchError } = useSessionStatus()
  const busy =
    status.state === 'active' ||
    status.state === 'logging_in' ||
    status.state === 'logging_out'
  const badgeState = fetchError ? 'offline' : stale ? 'stale' : status.state

  return (
    <main className="monitor">
      <header className="monitor-header">
        <p className="brand">fnguide-search-monitor</p>
        <h1>활성 세션</h1>
        <p className="lede">크롤 봇이 Fnguide에 붙어 있는지만 확인합니다.</p>
      </header>

      <section className={`panel badge-panel state-${badgeState}`}>
        <p className="badge-label">상태</p>
        <p className="badge-value">
          {fetchError
            ? 'API Offline'
            : stale
              ? 'Stale'
              : STATE_LABEL[status.state]}
        </p>
        {busy && !fetchError && !stale ? (
          <p className="warn">
            봇이 세션을 사용 중입니다. 같은 계정으로 수동 로그인하지 마세요.
          </p>
        ) : null}
        {stale && !fetchError ? (
          <p className="warn">
            heartbeat가 끊겼습니다. 봇이 비정상 종료됐을 수 있습니다.
          </p>
        ) : null}
        {fetchError ? (
          <p className="warn">API 연결 실패: {fetchError}</p>
        ) : null}
      </section>

      <section className="panel details">
        <dl>
          <div>
            <dt>user_id</dt>
            <dd>{status.user_id ?? '—'}</dd>
          </div>
          <div>
            <dt>step</dt>
            <dd>{status.step ?? '—'}</dd>
          </div>
          <div>
            <dt>pid</dt>
            <dd>{status.pid ?? '—'}</dd>
          </div>
          <div>
            <dt>started_at</dt>
            <dd>{formatTime(status.started_at)}</dd>
          </div>
          <div>
            <dt>updated_at</dt>
            <dd>{formatTime(status.updated_at)}</dd>
          </div>
          <div className="wide">
            <dt>current_url</dt>
            <dd className="mono">{status.current_url ?? '—'}</dd>
          </div>
          <div className="wide">
            <dt>message</dt>
            <dd>{status.message ?? '—'}</dd>
          </div>
        </dl>
      </section>
    </main>
  )
}

export default App
