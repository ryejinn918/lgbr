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
  PROFILE_MODE_LABEL,
  SEARCH_PROFILE_MODES,
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
    requestingClearError,
    startCrawl,
    requestLogout,
    clearError,
  } = useSessionStatus({ source: 'fnguide' })
  const profiles = useCrawlProfiles()

  const crawlMode = crawl.crawl?.mode ?? null
  const isMine = isFnguideCrawlMode(crawlMode)
  const crawlBusy =
    crawl.state === 'starting' ||
    crawl.state === 'active' ||
    crawl.state === 'stopping'
  const fnguideBusy = crawlBusy && isMine
  const otherBusy = crawlBusy && !isMine
  const sessionOpen = status.session != null
  const blockedByError = crawl.state === 'error' && !crawlBusy
  // Own last-run stays visible when idle (same as media search job history).
  const showRunMeta = isMine || blockedByError
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
            const label = PROFILE_MODE_LABEL[p.mode] ?? p.mode
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
        ? 'FnGuide · 검색 중'
        : otherBusy
          ? 'FnGuide · 대기'
          : isMine
            ? `FnGuide · ${crawl.label}`
            : 'FnGuide · 유휴'

  async function onStart(mode: CrawlMode = 'ai') {
    const searchLabel = crawlModeTypeLabel(mode)
    const periodMonths =
      profiles.items.find((p) => p.mode === mode)?.period_months ?? 3
    if (
      !window.confirm(
        `FnGuide 검색을 시작할까요?\n${searchLabel} · 최근 ${periodMonths}개월`,
      )
    ) {
      return
    }
    try {
      await startCrawl(mode)
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '실행 실패')
    }
  }

  async function onStop() {
    if (!window.confirm('FnGuide 검색을 종료하고 로그아웃할까요?')) return
    try {
      await requestLogout()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '종료 요청 실패')
    }
  }

  async function onClearError() {
    if (
      !window.confirm(
        '오류 상태를 해제하고 다시 시작할 수 있게 할까요?\n원인 확인 후 재실행하세요.',
      )
    ) {
      return
    }
    try {
      await clearError()
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '오류 해제 실패')
    }
  }

  return (
    <>
      <section className={`panel badge-panel state-${badgeState}`}>
        <p className="badge-label">검색 · 실행</p>
        <p className="badge-value">{badgeValue}</p>
        <p className="account-line">
          프로필 검색으로 목록을 모아 요약을 만듭니다.
        </p>
        <p className={`account-line state-${SESSION_CLASS[status.state]}`}>
          계정: {fetchError ? '—' : status.label}
        </p>
        {showRunMeta && crawl.crawl?.started_at && !fetchError ? (
          <p className="account-line">
            검색 시작 {formatTime(crawl.crawl.started_at)}
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
          </p>
        ) : null}
        {showRunMeta && resultLine && !fetchError ? (
          <p className="account-line">결과: {resultLine}</p>
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
              {resultLine ? `: ${resultLine}` : '.'} 원인을 확인한 뒤 「오류
              해제」를 누르면 다시 시작할 수 있습니다.
            </p>
          </div>
        ) : null}
        {!canStart && !crawlBusy && !blockedByError && !fetchError ? (
          <p className="warn">
            FnGuide 계정 세션이 남아 있어 실행할 수 없습니다.
          </p>
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
          {SEARCH_PROFILE_MODES.map((mode) => (
            <button
              key={mode}
              type="button"
              className="run-btn"
              disabled={!canStart || requestingStart || !!fetchError}
              onClick={() => void onStart(mode)}
            >
              {requestingStart ? '시작 중…' : PROFILE_MODE_LABEL[mode]}
            </button>
          ))}
          <button
            type="button"
            className="logout-btn"
            disabled={!canStop || requestingStop || !!fetchError}
            onClick={() => void onStop()}
          >
            {requestingStop ? '요청 중…' : '검색 중단'}
          </button>
          {blockedByError ? (
            <button
              type="button"
              className="logout-btn"
              disabled={requestingClearError || !!fetchError}
              onClick={() => void onClearError()}
            >
              {requestingClearError ? '해제 중…' : '오류 해제'}
            </button>
          ) : null}
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
