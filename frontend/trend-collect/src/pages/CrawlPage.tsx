import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCrawlProfiles } from '../hooks/useCrawlProfiles'
import { useSessionStatus } from '../hooks/useSessionStatus'
import type { CrawlMode } from '../types'
import {
  CRAWL_CLASS,
  SESSION_CLASS,
  formatCrawlResult,
  formatProgress,
  formatTime,
} from '../lib/format'
import {
  SEARCH_PROFILE_MODES,
  THEME_LABEL,
  isSearchProfileMode,
} from '../lib/themes'
import { crawlModeTypeLabel, isFnguideCrawlMode } from '../lib/collectNav'

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
  const profiles = useCrawlProfiles()
  const [debugMode, setDebugMode] = useState(false)

  const crawlMode = crawl.crawl?.mode ?? null
  const isMine = isFnguideCrawlMode(crawlMode)
  const crawlBusy =
    crawl.state === 'starting' ||
    crawl.state === 'active' ||
    crawl.state === 'stopping'
  const fnguideBusy = crawlBusy && isMine
  const otherBusy = crawlBusy && !isMine
  const sessionOpen = status.session != null
  const blockedByError = isMine && crawl.state === 'error'
  // Own last-run stays visible when idle (same as media search job history).
  const showRunMeta = isMine
  const showLiveCdp =
    fnguideBusy &&
    !!(crawl.crawl?.cdp_port || crawl.crawl?.cdp_http_url)
  const canStart = crawl.can_start === true && !crawlBusy
  const canStop = crawlBusy || sessionOpen
  const resultLine = showRunMeta
    ? formatCrawlResult(
        crawl.progress ?? crawl.crawl?.progress ?? undefined,
        crawl.crawl?.message,
      )
    : null
  const profileSummary =
    !profiles.error && profiles.items.length > 0
      ? profiles.items
          .filter((p) => isSearchProfileMode(p.mode))
          .map((p) => {
            const label = THEME_LABEL[p.mode] ?? p.mode
            const kw = p.keywords[0] ?? '—'
            const extra =
              p.keywords.length > 1 ? ` 외 ${p.keywords.length - 1}` : ''
            const sectors =
              p.sectors.length > 0 ? ` · 섹터 ${p.sectors.length}` : ''
            return `${label} 「${kw}${extra}」 ${p.period_months}개월 · ${p.page_min_label}${sectors}`
          })
          .join(' / ')
      : null
  const badgeState = fetchError
    ? 'offline'
    : fnguideBusy && stale
      ? 'stale'
      : fnguideBusy || blockedByError
        ? CRAWL_CLASS[crawl.state]
        : 'ended'
  const badgeValue = fetchError
    ? 'API Offline'
    : fnguideBusy && stale
      ? '응답 없음'
      : fnguideBusy || blockedByError
        ? `FnGuide · ${crawl.label}`
        : otherBusy
          ? 'FnGuide · 대기 (다른 세션이 브라우저 사용 중)'
          : isMine
            ? `FnGuide · ${crawl.label}`
            : 'FnGuide · 유휴'

  async function onStart(mode: CrawlMode = 'ai') {
    const searchLabel = crawlModeTypeLabel(mode)
    const periodMonths =
      profiles.items.find((p) => p.mode === mode)?.period_months ?? 3
    const label = debugMode
      ? `${searchLabel} ${periodMonths}개월치 다운로드 후 debug(CDP)로 전환할까요?`
      : `${searchLabel} ${periodMonths}개월치 리포트를 다운로드할까요?`
    if (!window.confirm(label)) {
      return
    }
    try {
      await startCrawl(mode, {
        debug: isSearchProfileMode(mode) ? debugMode : false,
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
      <section className={`panel badge-panel state-${badgeState}`}>
        <p className="badge-label">검색 · 실행</p>
        <p className="badge-value">{badgeValue}</p>
        <p className="account-line">
          프로필 검색으로 리포트를 받습니다. debug·애드혹은 CDP로 브라우저를
          엽니다.
        </p>
        <p className={`account-line state-${SESSION_CLASS[status.state]}`}>
          계정: {fetchError ? '—' : status.label}
        </p>
        {showRunMeta && crawl.crawl?.started_at && !fetchError ? (
          <p className="account-line">
            시작 {formatTime(crawl.crawl.started_at)}
            {crawl.crawl.ended_at
              ? ` · 종료 ${formatTime(crawl.crawl.ended_at)}`
              : ''}
          </p>
        ) : null}
        {showRunMeta && crawl.crawl?.mode && !fetchError ? (
          <p className="account-line">
            모드: {crawlModeTypeLabel(crawl.crawl.mode)}
            {isSearchProfileMode(crawl.crawl.mode) && crawl.crawl.period_months
              ? ` · ${crawl.crawl.period_months}개월`
              : ''}
            {crawl.crawl.debug ? ' · debug' : ''}
            {fnguideBusy && crawl.crawl.cdp_port
              ? ` · CDP ${crawl.crawl.cdp_port}`
              : fnguideBusy &&
                  (crawl.crawl.mode === 'adhoc' || crawl.crawl.debug)
                ? ' · CDP 대기'
                : ''}
          </p>
        ) : null}
        {showRunMeta && crawl.crawl?.asset_id && !fetchError ? (
          <p className="account-line">애셋: {crawl.crawl.asset_id}</p>
        ) : null}
        {showRunMeta && resultLine && !fetchError ? (
          <p className="account-line">결과: {resultLine}</p>
        ) : null}
        {showLiveCdp && crawl.crawl?.cdp_http_url && !fetchError ? (
          <p className="account-line">CDP: {crawl.crawl.cdp_http_url}</p>
        ) : null}
        {fnguideBusy && !fetchError ? (
          <p className="account-line">{formatProgress(crawl.progress)}</p>
        ) : null}
        {otherBusy && !fetchError ? (
          <p className="account-line">
            다른 매체가 브라우저 세션을 사용 중입니다. FnGuide 검색은 종료 후
            시작할 수 있습니다.
          </p>
        ) : null}
        {fnguideBusy && crawl.state === 'active' && !fetchError ? (
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
        {fnguideBusy && stale && !fetchError ? (
          <p className="warn">최근 활동 갱신이 없습니다.</p>
        ) : null}
        {fetchError ? <p className="warn">API 연결 실패: {fetchError}</p> : null}

        {profileSummary ? (
          <p className="account-line profile-summary">
            필터: {profileSummary}{' '}
            <Link to="/collect/fnguide/list/search/types">프로필</Link>
          </p>
        ) : null}
        <p className="account-line">
          {!profileSummary ? (
            <>
              <Link to="/collect/fnguide/list/search/types">
                프로필·필터 설정
              </Link>
              {' · '}
            </>
          ) : null}
          문서: <Link to="/docs/reports/fnguide">FnGuide 보고서</Link>
        </p>

        <div className="actions">
          <label className="limit-field">
            <span>debug</span>
            <input
              type="checkbox"
              checked={debugMode}
              disabled={!canStart || requestingStart || !!fetchError}
              onChange={(e) => setDebugMode(e.target.checked)}
            />
          </label>
          {SEARCH_PROFILE_MODES.map((mode) => (
            <button
              key={mode}
              type="button"
              className="run-btn"
              disabled={!canStart || requestingStart || !!fetchError}
              onClick={() => void onStart(mode)}
            >
              {requestingStart ? '시작 중…' : THEME_LABEL[mode]}
            </button>
          ))}
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
              {formatTime(
                showRunMeta
                  ? (crawl.crawl?.started_at ?? status.session?.started_at)
                  : status.session?.started_at,
              )}
            </dd>
          </div>
          <div>
            <dt>최근 사용</dt>
            <dd>{formatTime(status.session?.last_used_at)}</dd>
          </div>
          <div>
            <dt>진행</dt>
            <dd>
              {fetchError || !fnguideBusy
                ? '—'
                : formatProgress(crawl.progress)}
            </dd>
          </div>
        </dl>
      </section>
    </>
  )
}
