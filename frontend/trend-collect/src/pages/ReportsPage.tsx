import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type MouseEvent,
} from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAudit } from '../hooks/useAudit'
import { useReports } from '../hooks/useReports'
import { useSessionStatus } from '../hooks/useSessionStatus'
import {
  QUALITY_LABEL,
  STATUS_LABEL,
  THEME_LABEL,
  formatAuditStats,
  formatPublishedAt,
  formatRelative,
  formatTime,
  qualityLabelForReport,
  qualityLabelsForSource,
} from '../lib/format'
import { reportPublicOriginalUrl } from '../lib/publicOriginalUrl'
import {
  QUALITY_FILTERS,
  STATUS_FILTERS,
  THEME_FILTERS,
  isReportFiltersDirty,
  isUnauditedPreset,
  parseReportFilters,
  resetReportFilters,
  resolveReportSort,
  serializeReportFilters,
  unauditedPreset,
  withPage,
  withQuality,
  withQuery,
  withSort,
  withStatus,
  withTheme,
  type ReportFilters,
} from '../lib/reportFilters'
import type { QualityJson, ReportRecord } from '../types'

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((x) => String(x)).filter(Boolean)
}

const SOURCE_LABEL: Record<string, string> = {
  all: '보고서 통합',
  fnguide: 'FnGuide',
  pwc: 'PwC',
  accenture: 'Accenture',
  kpmg: 'KPMG',
  ey: 'EY',
  deloitte: 'Deloitte',
  mckinsey: 'McKinsey',
  bain: 'Bain',
  bcg: 'BCG',
  hbr: 'HBR',
  hbrkorea: 'HBR Korea',
}

export function ReportsPage({
  embedded = false,
  source = 'all',
}: {
  embedded?: boolean
  source?: string
}) {
  const [params, setParams] = useSearchParams()
  const searchKey = params.toString()
  const filters = useMemo(
    () => parseReportFilters(new URLSearchParams(searchKey)),
    [searchKey],
  )
  const [qDraft, setQDraft] = useState(filters.q)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detailTick, setDetailTick] = useState(0)
  const [detail, setDetail] = useState<ReportRecord | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const { crawl } = useSessionStatus()
  const audit = useAudit()
  const crawlBusy =
    crawl.state === 'starting' ||
    crawl.state === 'active' ||
    crawl.state === 'stopping'
  const dirty = isReportFiltersDirty(filters, qDraft)
  const unauditedActive = isUnauditedPreset(filters)

  useEffect(() => {
    setQDraft(filters.q)
  }, [filters.q])

  const query = useMemo(
    () => ({
      source,
      status: filters.status,
      quality: filters.quality,
      theme: filters.theme,
      q: filters.q,
      sort: resolveReportSort(filters.sort),
      limit: 30,
      offset: filters.offset,
      poll: true,
    }),
    [filters, source],
  )
  const reports = useReports(query)

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      setDetailError(null)
      setDetailLoading(false)
      return
    }
    let cancelled = false
    setDetailLoading(true)
    setDetailError(null)
    void fetch(`/api/reports/${selectedId}`)
      .then(async (res) => {
        const data = (await res.json()) as {
          ok?: boolean
          message?: string
          report?: ReportRecord
        }
        if (!res.ok) {
          throw new Error(data.message || `HTTP ${res.status}`)
        }
        if (!cancelled) {
          setDetail(data.report ?? null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setDetail(null)
          setDetailError(err instanceof Error ? err.message : '상세 로드 실패')
        }
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedId, detailTick])

  const prevAuditState = useRef(audit.state)
  useEffect(() => {
    const prev = prevAuditState.current
    prevAuditState.current = audit.state
    if (!selectedId) return
    if (
      (audit.state === 'ended' || audit.state === 'error') &&
      prev !== audit.state
    ) {
      setDetailTick((n) => n + 1)
      void reports.refresh()
    }
  }, [audit.state, selectedId, reports.refresh])

  function commit(next: ReportFilters) {
    setQDraft(next.q)
    const serialized = serializeReportFilters(next)
    if ([...serialized.keys()].length === 0) {
      setParams({}, { replace: true })
      return
    }
    setParams(serialized, { replace: true })
  }

  function onSearch(e: FormEvent) {
    e.preventDefault()
    commit(withQuery(filters, qDraft))
  }

  function onRowClick(id: string) {
    setSelectedId((prev) => (prev === id ? null : id))
  }

  function onFileClick(e: MouseEvent) {
    e.stopPropagation()
  }

  async function onStartPending() {
    const ok = await audit.startPending({
      theme: filters.theme !== 'all' ? filters.theme : undefined,
    })
    if (ok) void reports.refresh()
  }

  async function onReauditSelected() {
    if (!selectedId) return
    const ok = await audit.startOne(selectedId)
    if (ok) void reports.refresh()
  }

  const qj: QualityJson = detail?.quality_json || {}
  const failReasons = stringList(qj.fail_reasons)
  const passSignals = stringList(qj.pass_signals)
  const detailOriginalUrl = reportPublicOriginalUrl(
    detail?.source,
    detail?.url,
  )
  const sourceKey = source || 'all'
  const isAll = sourceKey === 'all'
  // 증권사 열은 FnGuide 단독 탭만. 통합 보기·Big4에는 숨김.
  const showProvider = sourceKey === 'fnguide'
  const isSellSidePage = sourceKey === 'fnguide'
  // 통합 탭 필터는 기존 판정 어휘 유지; 매체 단독 탭만 요약 라벨.
  const qualityFilterLabels = isSellSidePage
    ? QUALITY_LABEL
    : isAll
      ? QUALITY_LABEL
      : qualityLabelsForSource(sourceKey)
  const detailIsSellSide =
    isSellSidePage ||
    (isAll && (detail?.source || '') === 'fnguide')
  const detailSummary = String(
    qj.summary || qj.framework_summary || '',
  ).trim()
  const detailThemes = (
    detail?.themes?.length
      ? detail.themes
      : stringList(qj.themes)
  ).filter(Boolean)
  const sourceTitle = SOURCE_LABEL[sourceKey] ?? sourceKey
  const sourceLede = isAll
    ? '매체별 보고서를 한곳에서 봅니다. FnGuide·PwC·Accenture·KPMG·EY·Deloitte·HBR Korea 탭으로 나눌 수도 있습니다.'
    : sourceKey === 'pwc'
      ? '삼일PwC Insights 목록입니다. 검색 실행이 목록을 넘기며 PDF를 받습니다.'
      : sourceKey === 'accenture'
        ? 'Accenture US Research Report 목록입니다. 검색 실행이 목록을 넘기며 PDF를 받습니다.'
        : sourceKey === 'kpmg'
          ? 'KPMG US Insights 목록입니다. 검색 실행이 목록을 넘기며 PDF를 받습니다.'
          : sourceKey === 'ey'
            ? 'EY US Insights 목록입니다. 검색 실행이 목록을 넘기며 PDF를 받습니다.'
            : sourceKey === 'deloitte'
              ? 'Deloitte US Insights 목록입니다. 검색 실행이 목록을 넘기며 PDF를 받습니다.'
              : sourceKey === 'bain'
                ? 'Bain Insights 목록입니다. 브라우저로 한 건씩 PDF/page.pdf를 받습니다.'
                : sourceKey === 'bcg'
                  ? 'BCG Featured Insights 목록입니다. 브라우저로 한 건씩 PDF/page.pdf를 받습니다.'
                  : sourceKey === 'hbr'
                    ? 'HBR.org 목록입니다. 로그인 후 Latest를 돌며 page.pdf를 받습니다.'
                    : sourceKey === 'hbrkorea'
                      ? 'HBR Korea 목록입니다. 로그인 검색이 목록을 돌며 page.pdf를 받습니다.'
                      : '증권사 리포트 목록입니다. 업종 분석에 쓸 만한지 품질 감사한 결과가 함께 표시됩니다.'
  const collectHref = isAll
    ? '/collect'
    : `/collect/${sourceKey}/list/search`

  return (
    <>
      {embedded ? (
        <div className="section-head" style={{ marginBottom: '0.75rem' }}>
          <h2>{sourceTitle}</h2>
          <span className="section-note">
            목록·다운로드·품질 감사 ·{' '}
            <Link to={collectHref}>{isAll ? '수집' : '검색 실행'}</Link>
          </span>
        </div>
      ) : (
        <header className="monitor-header">
          <h1>{sourceTitle}</h1>
          <p className="lede">{sourceLede}</p>
        </header>
      )}

      {crawlBusy && crawl.crawl ? (
        <p className="panel live-banner">
          수집 중: {crawl.crawl.mode}
          {crawl.crawl.asset_id ? ` · ${crawl.crawl.asset_id}` : ''}
          {' · '}
          <Link to="/">대시보드에서 보기</Link>
        </p>
      ) : null}

      <section className="panel audit-bar">
        <div className="audit-bar-row">
          <div>
            <strong>품질 감사</strong>
            <span className="section-note">
              {' '}
              · {audit.label}
              {audit.message ? ` — ${audit.message}` : ''}
            </span>
            <p className="section-note" style={{ margin: '0.35rem 0 0' }}>
              {isSellSidePage
                ? '본문 PDF가 있는 리포트만 자동으로 품질 감사합니다. 적합 판정만 컨센서스 입력에 쓰입니다.'
                : isAll
                  ? '본문 PDF가 있는 리포트만 자동으로 품질 감사합니다. FnGuide는 적합/부적합, 그 외 매체는 요약·섹터를 추출합니다.'
                  : '본문 PDF가 있는 문헌만 자동으로 요약·섹터를 추출합니다.'}
            </p>
          </div>
          <div className="audit-actions">
            <button
              type="button"
              className={`filter-chip${unauditedActive ? ' active' : ''}`}
              onClick={() =>
                commit(
                  unauditedActive
                    ? resetReportFilters()
                    : unauditedPreset(filters),
                )
              }
              title="다운로드된 미감사 리포트만 보기"
            >
              미감사만 보기
            </button>
            <button
              type="button"
              className="run-btn"
              disabled={audit.busy}
              onClick={() => void onStartPending()}
              title={
                filters.theme !== 'all'
                  ? `${THEME_LABEL[filters.theme]} 미감사만 일괄 실행`
                  : '다운로드된 미감사 전부 일괄 실행'
              }
            >
              {audit.busy ? '감사 중…' : '미감사 일괄 실행'}
            </button>
          </div>
        </div>
        {audit.error ? <p className="warn">{audit.error}</p> : null}
        {formatAuditStats(audit.audit?.stats) ? (
          <p className="section-note">
            최근 결과: {formatAuditStats(audit.audit?.stats)}
          </p>
        ) : null}
      </section>

      <section className="panel">
        <div className="filter-row">
          {STATUS_FILTERS.map((key) => (
            <button
              key={key}
              type="button"
              className={`filter-chip${filters.status === key ? ' active' : ''}`}
              onClick={() => commit(withStatus(filters, key))}
            >
              {STATUS_LABEL[key]} {reports.counts[key] ?? 0}
            </button>
          ))}
          <button
            type="button"
            className="filter-chip filter-reset"
            disabled={!dirty}
            onClick={() => commit(resetReportFilters())}
            title="상태·테마·판정·검색·정렬·페이지 초기화"
          >
            초기화
          </button>
        </div>
        <div className="filter-row">
          {THEME_FILTERS.map((key) => (
            <button
              key={key}
              type="button"
              className={`filter-chip${filters.theme === key ? ' active' : ''}`}
              onClick={() => commit(withTheme(filters, key))}
            >
              {THEME_LABEL[key]} {reports.themeCounts[key] ?? 0}
            </button>
          ))}
          <span className="filter-row-note">(중복가능)</span>
        </div>
        <div className="filter-row">
          {QUALITY_FILTERS.map((key) => (
            <button
              key={key}
              type="button"
              className={`filter-chip${filters.quality === key ? ' active' : ''}`}
              onClick={() => commit(withQuality(filters, key))}
            >
              {qualityFilterLabels[key] || QUALITY_LABEL[key]}{' '}
              {key === 'all'
                ? (reports.qualityCounts.pass ?? 0) +
                  (reports.qualityCounts.fail ?? 0) +
                  (reports.qualityCounts.pending ?? 0) +
                  (reports.qualityCounts.unauditable ?? 0)
                : (reports.qualityCounts[key] ?? 0)}
            </button>
          ))}
        </div>
        <form className="search-row" onSubmit={onSearch}>
          <input
            type="search"
            placeholder={
              showProvider ? '제목, 인용 제목, 증권사' : '제목, 인용 제목'
            }
            value={qDraft}
            onChange={(e) => setQDraft(e.target.value)}
          />
          <button type="submit" className="run-btn">
            검색
          </button>
          {filters.q || qDraft ? (
            <button
              type="button"
              className="run-btn"
              onClick={() => commit(withQuery(filters, ''))}
            >
              검색 지우기
            </button>
          ) : null}
          <button
            type="button"
            className="run-btn"
            onClick={() => void reports.refresh()}
          >
            새로고침
          </button>
        </form>
        {reports.error ? <p className="warn">{reports.error}</p> : null}
        {reports.loading && reports.items.length === 0 ? (
          <p className="empty">불러오는 중…</p>
        ) : reports.items.length === 0 ? (
          <p className="empty">결과가 없습니다.</p>
        ) : (
          <div className="report-sheet">
            <table className="report-table report-table-audit">
              <thead>
                <tr>
                  <th className="col-status">상태</th>
                  <th className="col-quality">
                    {isSellSidePage ? '판정' : isAll ? '판정/요약' : '요약'}
                  </th>
                  <th className="col-title">제목</th>
                  {showProvider ? (
                    <th className="col-provider">증권사</th>
                  ) : null}
                  <th className="col-published">
                    <button
                      type="button"
                      className={`sort-th${filters.sort === 'published_at' ? ' active' : ''}`}
                      onClick={() => commit(withSort(filters, 'published_at'))}
                      title="발행일 내림차순 (다시 누르면 해제)"
                    >
                      발행일{filters.sort === 'published_at' ? ' ↓' : ''}
                    </button>
                  </th>
                  <th className="col-pages">
                    <button
                      type="button"
                      className={`sort-th${filters.sort === 'page_count' ? ' active' : ''}`}
                      onClick={() => commit(withSort(filters, 'page_count'))}
                      title="페이지수 내림차순 (다시 누르면 해제)"
                    >
                      페이지{filters.sort === 'page_count' ? ' ↓' : ''}
                    </button>
                  </th>
                  {isAll ? <th className="col-source">매체</th> : null}
                  <th className="col-qat">감사일</th>
                  <th className="col-seen">
                    <button
                      type="button"
                      className={`sort-th${filters.sort === 'last_seen_at' ? ' active' : ''}`}
                      onClick={() => commit(withSort(filters, 'last_seen_at'))}
                      title="최근 본 시각 내림차순 (다시 누르면 해제)"
                    >
                      최근{filters.sort === 'last_seen_at' ? ' ↓' : ''}
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {reports.items.map((item) => {
                  const q = item.quality || 'pending'
                  const selected = selectedId === item.id
                  const originalUrl = reportPublicOriginalUrl(
                    item.source,
                    item.url,
                  )
                  return (
                    <tr
                      key={item.id}
                      className={selected ? 'row-selected' : undefined}
                      onClick={() => onRowClick(item.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="col-status">
                        <span className={`status-pill status-${item.status}`}>
                          {STATUS_LABEL[item.status] || item.status}
                        </span>
                      </td>
                      <td className="col-quality">
                        <span className={`status-pill quality-${q}`}>
                          {qualityLabelForReport(q, item.source, sourceKey)}
                        </span>
                      </td>
                      <td className="col-title report-title">
                        <div className="report-title-inner">
                          <span
                            className="report-title-text"
                            title={item.title}
                          >
                            {item.title}
                          </span>
                          {(item.themes || []).length > 0 ? (
                            <span className="report-title-meta">
                              {(item.themes || []).map((t) => (
                                <span key={t} className="theme-chip">
                                  {THEME_LABEL[t] || t}
                                </span>
                              ))}
                            </span>
                          ) : null}
                          {originalUrl ? (
                            <a
                              className="report-file-link report-original-link"
                              href={originalUrl}
                              target="_blank"
                              rel="noreferrer"
                              onClick={onFileClick}
                            >
                              원문
                            </a>
                          ) : null}
                        </div>
                      </td>
                      {showProvider ? (
                        <td
                          className="col-provider"
                          title={item.provider || undefined}
                        >
                          {item.provider || '—'}
                        </td>
                      ) : null}
                      <td className="col-published mono">
                        {formatPublishedAt(item.published_at)}
                      </td>
                      <td className="col-pages mono report-pages">
                        {item.page_count != null ? item.page_count : '—'}
                      </td>
                      {isAll ? (
                        <td className="col-source">
                          {SOURCE_LABEL[item.source || ''] ||
                            item.source ||
                            '—'}
                        </td>
                      ) : null}
                      <td
                        className="col-qat"
                        title={item.quality_at || undefined}
                      >
                        {formatRelative(item.quality_at)}
                      </td>
                      <td
                        className="col-seen"
                        title={item.last_seen_at || undefined}
                      >
                        {formatRelative(item.last_seen_at)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        <div className="pager">
          <button
            type="button"
            className="run-btn"
            disabled={filters.offset <= 0}
            onClick={() => commit(withPage(filters, -1, reports.limit))}
          >
            이전
          </button>
          <span className="section-note">
            {filters.offset + 1}–
            {Math.min(filters.offset + reports.limit, reports.total)} /{' '}
            {reports.total}
          </span>
          <button
            type="button"
            className="run-btn"
            disabled={filters.offset + reports.limit >= reports.total}
            onClick={() => commit(withPage(filters, 1, reports.limit))}
          >
            다음
          </button>
        </div>
      </section>

      {selectedId ? (
        <section className="panel audit-detail">
          <div className="section-head">
            <h2>품질 감사 결과</h2>
            <div className="audit-actions">
              {detailOriginalUrl ? (
                <a
                  className="run-btn"
                  href={detailOriginalUrl}
                  target="_blank"
                  rel="noreferrer"
                  onClick={onFileClick}
                >
                  원문 열기
                </a>
              ) : null}
              <button
                type="button"
                className="run-btn"
                disabled={audit.busy || !detail?.has_file}
                onClick={() => void onReauditSelected()}
              >
                다시 감사
              </button>
              <button
                type="button"
                className="run-btn"
                onClick={() => setSelectedId(null)}
              >
                닫기
              </button>
            </div>
          </div>
          {detailLoading ? <p className="empty">불러오는 중…</p> : null}
          {detailError ? <p className="warn">{detailError}</p> : null}
          {detail && !detailLoading ? (
            <div className="details">
              <dl>
                <div>
                  <dt>제목</dt>
                  <dd>{detail.title}</dd>
                </div>
                <div>
                  <dt>{detailIsSellSide ? '판정' : '상태'}</dt>
                  <dd>
                    {qualityLabelForReport(
                      detail.quality,
                      detail.source,
                      sourceKey,
                    )}
                  </dd>
                </div>
                <div>
                  <dt>감사 시각</dt>
                  <dd>{formatTime(detail.quality_at)}</dd>
                </div>
                <div>
                  <dt>인용 제목</dt>
                  <dd>{String(qj.short_title || '—')}</dd>
                </div>
                {detailIsSellSide ? (
                  <>
                    <div>
                      <dt>주제</dt>
                      <dd>{String(qj.topic || '—')}</dd>
                    </div>
                    <div>
                      <dt>분석 틀 요약</dt>
                      <dd>{String(qj.framework_summary || '—')}</dd>
                    </div>
                    <div>
                      <dt>부적합 사유</dt>
                      <dd>
                        {failReasons.length ? (
                          <ul className="audit-list">
                            {failReasons.map((r) => (
                              <li key={r}>{r}</li>
                            ))}
                          </ul>
                        ) : (
                          '—'
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>적합 근거</dt>
                      <dd>
                        {passSignals.length ? (
                          <ul className="audit-list">
                            {passSignals.map((r) => (
                              <li key={r}>{r}</li>
                            ))}
                          </ul>
                        ) : (
                          '—'
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>판정 설명</dt>
                      <dd className="audit-rationale">
                        {String(qj.rationale || qj.error || '—')}
                      </dd>
                    </div>
                  </>
                ) : (
                  <>
                    <div>
                      <dt>섹터</dt>
                      <dd>
                        {detailThemes.length ? (
                          <span className="theme-chips">
                            {detailThemes.map((t) => (
                              <span key={t} className="theme-chip">
                                {THEME_LABEL[t] || t}
                              </span>
                            ))}
                          </span>
                        ) : (
                          '—'
                        )}
                      </dd>
                    </div>
                    <div className="details-span">
                      <dt>요약</dt>
                      <dd className="audit-rationale">
                        {detailSummary || String(qj.error || '—')}
                      </dd>
                    </div>
                  </>
                )}
              </dl>
            </div>
          ) : null}
        </section>
      ) : null}
    </>
  )
}
