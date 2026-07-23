import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCrawlProfiles } from '../hooks/useCrawlProfiles'
import { useSessionStatus } from '../hooks/useSessionStatus'
import { useTimeline } from '../hooks/useTimeline'
import type { CrawlMode, TimelineItem, TimelineSession } from '../types'
import {
  CRAWL_CLASS,
  SESSION_CLASS,
  formatCrawlResult,
  formatEventDetail,
  formatProgress,
  formatTime,
} from '../lib/format'

export function CrawlPage() {
  const {
    crawl,
    status,
    stale,
    fetchError,
    requestingStart,
    requestingStop,
    startCrawl,
    requestLogout,
  } = useSessionStatus()
  const timeline = useTimeline({ limit: 10, eventLimit: 30 })
  const profiles = useCrawlProfiles()
  const [reportLimit, setReportLimit] = useState(5)
  const [debugMode, setDebugMode] = useState(false)
  const resultLine = formatCrawlResult(
    crawl.progress ?? crawl.crawl?.progress ?? undefined,
    crawl.crawl?.message,
  )

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
    const searchLabel =
      mode === 'ai'
        ? 'AI'
        : mode === 'physical_ai'
          ? 'Physical AI'
          : mode === 'datacenter'
            ? '데이터센터'
            : mode
    const isSearchMode =
      mode === 'datacenter' || mode === 'ai' || mode === 'physical_ai'
    const label =
      mode === 'adhoc'
        ? '애드혹 크롤을 시작할까요? (CDP 원격 조작, 로그인 세션 획득)'
        : debugMode
          ? `${searchLabel} ${limit}건 다운로드 후 debug(adhoc/CDP)로 전환할까요?`
          : `${searchLabel} 리포트 ${limit}건을 다운로드할까요?`
    if (!window.confirm(label)) {
      return
    }
    try {
      await startCrawl(mode, limit, {
        debug: isSearchMode ? debugMode : false,
      })
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
    <>
      <header className="monitor-header">
        <h1>크롤</h1>
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
            {(crawl.crawl.mode === 'datacenter' ||
              crawl.crawl.mode === 'ai' ||
              crawl.crawl.mode === 'physical_ai') &&
            crawl.crawl.report_limit
              ? ` · limit ${crawl.crawl.report_limit}`
              : ''}
            {crawl.crawl.debug ? ' · debug' : ''}
            {crawl.crawl.cdp_port
              ? ` · CDP ${crawl.crawl.cdp_port}`
              : crawl.crawl.mode === 'adhoc' || crawl.crawl.debug
                ? ' · CDP 대기'
                : ''}
          </p>
        ) : null}
        {crawl.crawl?.asset_id && !fetchError ? (
          <p className="account-line">애셋: {crawl.crawl.asset_id}</p>
        ) : null}
        {resultLine && !fetchError ? (
          <p className="account-line">결과: {resultLine}</p>
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
              {resultLine ? `: ${resultLine}` : '.'} 원인을 점검한 뒤, 아래 DB에
              접속해 <code>fnguide_crawls.state</code>를{' '}
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

        {!profiles.error && profiles.items.length > 0 ? (
          <p className="account-line profile-summary">
            필터:{' '}
            {profiles.items
              .map((p) => {
                const label =
                  p.mode === 'ai'
                    ? 'AI'
                    : p.mode === 'physical_ai'
                      ? 'Physical AI'
                      : '데이터센터'
                const sectors =
                  p.sectors.length > 0 ? ` · 섹터 ${p.sectors.length}` : ''
                return `${label} 「${p.keyword}」 ${p.period_months}개월 · ${p.page_min_label}${sectors}`
              })
              .join(' / ')}{' '}
            <Link to="/types">수정</Link>
          </p>
        ) : null}

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
          <label className="limit-field">
            <span>debug</span>
            <input
              type="checkbox"
              checked={debugMode}
              disabled={!canStart || requestingStart || !!fetchError}
              onChange={(e) => setDebugMode(e.target.checked)}
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
            onClick={() => void onStart('ai')}
          >
            {requestingStart ? '시작 중…' : 'AI'}
          </button>
          <button
            type="button"
            className="run-btn"
            disabled={!canStart || requestingStart || !!fetchError}
            onClick={() => void onStart('physical_ai')}
          >
            {requestingStart ? '시작 중…' : 'Physical AI'}
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
          <div>
            <dt>진행</dt>
            <dd>{fetchError ? '—' : formatProgress(crawl.progress)}</dd>
          </div>
        </dl>
      </section>

      <section className="panel history events">
        <h2>활동 타임라인</h2>
        <p className="section-note" style={{ marginTop: 0 }}>
          로그인 세션 단위로 묶입니다. 카드를 누르면 그 세션의 로그인·크롤
          이벤트를 봅니다.
        </p>
        {timeline.error ? <p className="warn">{timeline.error}</p> : null}
        {timeline.loading && timeline.sessions.length === 0 ? (
          <p className="empty">불러오는 중…</p>
        ) : timeline.sessions.length === 0 ? (
          <p className="empty">세션이 없습니다.</p>
        ) : (
          <>
            <div className="session-cards">
              {timeline.sessions.map((sess: TimelineSession) => {
                const expanded = timeline.expandedId === sess.id
                return (
                  <div
                    key={sess.id}
                    className={`session-card${expanded ? ' expanded' : ''}`}
                  >
                    <button
                      type="button"
                      className="session-card-head"
                      onClick={() => timeline.setExpandedId(sess.id)}
                    >
                      <div className="history-main">
                        <span className="history-label">{sess.label}</span>
                        <span className="history-user">
                          {sess.fnguide_user_id || '—'}
                        </span>
                      </div>
                      <div className="history-meta">
                        {formatTime(sess.started_at)} ~{' '}
                        {formatTime(sess.ended_at)}
                        {sess.end_reason_label
                          ? ` · ${sess.end_reason_label}`
                          : ''}
                        {` · 이벤트 ${sess.event_count} · 크롤 ${sess.crawl_count}`}
                      </div>
                    </button>
                    {expanded ? (
                      <div className="session-card-body">
                        {timeline.eventsError ? (
                          <p className="warn">{timeline.eventsError}</p>
                        ) : null}
                        {timeline.eventsLoading &&
                        timeline.events.length === 0 ? (
                          <p className="empty">이벤트 불러오는 중…</p>
                        ) : timeline.events.length === 0 ? (
                          <p className="empty">이벤트가 없습니다.</p>
                        ) : (
                          <>
                            <ul>
                              {timeline.events.map((item: TimelineItem) => (
                                <li
                                  key={`${item.kind}-${item.id}`}
                                  className={`event-level-${item.level || item.kind}`}
                                >
                                  <div className="history-main">
                                    <span
                                      className={`kind-pill kind-${item.kind}`}
                                    >
                                      {item.kind_label}
                                    </span>
                                    <span className="history-label">
                                      {item.label}
                                    </span>
                                    {item.level ? (
                                      <span className="history-user">
                                        {item.level}
                                      </span>
                                    ) : null}
                                  </div>
                                  <div className="history-meta">
                                    {formatTime(item.at)}
                                    {formatEventDetail(item.detail)
                                      ? ` · ${formatEventDetail(item.detail)}`
                                      : ''}
                                  </div>
                                </li>
                              ))}
                            </ul>
                            <div className="pager">
                              <button
                                type="button"
                                className="run-btn"
                                disabled={timeline.eventsOffset <= 0}
                                onClick={() =>
                                  timeline.setEventsOffset(
                                    Math.max(
                                      0,
                                      timeline.eventsOffset -
                                        timeline.eventsLimit,
                                    ),
                                  )
                                }
                              >
                                이전
                              </button>
                              <span className="section-note">
                                {timeline.eventsOffset + 1}–
                                {Math.min(
                                  timeline.eventsOffset + timeline.eventsLimit,
                                  timeline.eventsTotal,
                                )}{' '}
                                / {timeline.eventsTotal}
                              </span>
                              <button
                                type="button"
                                className="run-btn"
                                disabled={
                                  timeline.eventsOffset +
                                    timeline.eventsLimit >=
                                  timeline.eventsTotal
                                }
                                onClick={() =>
                                  timeline.setEventsOffset(
                                    timeline.eventsOffset +
                                      timeline.eventsLimit,
                                  )
                                }
                              >
                                다음
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    ) : null}
                  </div>
                )
              })}
            </div>
            <div className="pager">
              <button
                type="button"
                className="run-btn"
                disabled={timeline.offset <= 0}
                onClick={() =>
                  timeline.setOffset(
                    Math.max(0, timeline.offset - timeline.limit),
                  )
                }
              >
                이전
              </button>
              <span className="section-note">
                {timeline.offset + 1}–
                {Math.min(timeline.offset + timeline.limit, timeline.total)} /{' '}
                {timeline.total}
              </span>
              <button
                type="button"
                className="run-btn"
                disabled={timeline.offset + timeline.limit >= timeline.total}
                onClick={() =>
                  timeline.setOffset(timeline.offset + timeline.limit)
                }
              >
                다음
              </button>
            </div>
          </>
        )}
      </section>
    </>
  )
}
