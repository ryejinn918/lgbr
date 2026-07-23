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
  formatPublishedAt,
  formatRelative,
  formatTime,
} from '../lib/format'
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

function formatConfidence(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toFixed(2)
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((x) => String(x)).filter(Boolean)
}

export function ReportsPage() {
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
      status: filters.status,
      quality: filters.quality,
      theme: filters.theme,
      q: filters.q,
      sort: resolveReportSort(filters.sort),
      limit: 30,
      offset: filters.offset,
      poll: true,
    }),
    [filters],
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

  return (
    <>
      <header className="monitor-header">
        <h1>보고서</h1>
        <p className="lede">
          리스트·다운로드·품질 감사 상태가 기록된 전체 카탈로그입니다.
        </p>
      </header>

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
              title="status=downloaded + quality=pending"
            >
              미감사 큐
            </button>
            <button
              type="button"
              className="run-btn"
              disabled={audit.busy}
              onClick={() => void onStartPending()}
              title={
                filters.theme !== 'all'
                  ? `테마 ${THEME_LABEL[filters.theme]} 미감사만`
                  : '다운로드된 미감사 전부'
              }
            >
              {audit.busy ? '감사 중…' : '미감사 실행'}
            </button>
          </div>
        </div>
        {audit.error ? <p className="warn">{audit.error}</p> : null}
        {audit.audit?.stats ? (
          <p className="section-note">
            최근 결과: candidates={audit.audit.stats.candidates ?? 0} pass=
            {audit.audit.stats.pass ?? 0} reject={audit.audit.stats.reject ?? 0}{' '}
            extract_fail={audit.audit.stats.extract_fail ?? 0} fail_api=
            {audit.audit.stats.fail_api ?? 0}
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
            title="상태·테마·품질·검색·정렬·페이지 초기화"
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
        </div>
        <div className="filter-row">
          {QUALITY_FILTERS.map((key) => (
            <button
              key={key}
              type="button"
              className={`filter-chip${filters.quality === key ? ' active' : ''}`}
              onClick={() => commit(withQuality(filters, key))}
            >
              {QUALITY_LABEL[key]}{' '}
              {key === 'all'
                ? (reports.qualityCounts.pass ?? 0) +
                  (reports.qualityCounts.fail ?? 0) +
                  (reports.qualityCounts.pending ?? 0)
                : (reports.qualityCounts[key] ?? 0)}
            </button>
          ))}
        </div>
        <form className="search-row" onSubmit={onSearch}>
          <input
            type="search"
            placeholder="제목, 증권사, rpt_id"
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
                  <th className="col-quality">품질</th>
                  <th className="col-scope">scope</th>
                  <th className="col-conf">conf</th>
                  <th className="col-title">제목</th>
                  <th className="col-provider">증권사</th>
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
                  <th className="col-rpt">rpt_id</th>
                  <th className="col-file">파일</th>
                  <th className="col-qat">감사</th>
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
                        <span
                          className={`status-pill quality-${q}`}
                          title={
                            item.quality_scope
                              ? `scope=${item.quality_scope}`
                              : undefined
                          }
                        >
                          {QUALITY_LABEL[q] || q}
                        </span>
                      </td>
                      <td className="col-scope mono">
                        {item.quality_scope || '—'}
                      </td>
                      <td className="col-conf mono">
                        {formatConfidence(item.quality_confidence)}
                      </td>
                      <td className="col-title report-title" title={item.title}>
                        {item.title}
                      </td>
                      <td
                        className="col-provider"
                        title={item.provider || undefined}
                      >
                        {item.provider || '—'}
                      </td>
                      <td className="col-published mono">
                        {formatPublishedAt(item.published_at)}
                      </td>
                      <td className="col-pages mono report-pages">
                        {item.page_count != null ? item.page_count : '—'}
                      </td>
                      <td className="col-rpt mono" title={item.source_key}>
                        {item.source_key}
                      </td>
                      <td className="col-file">
                        {item.has_file ? (
                          <a
                            className="report-file-link"
                            href={`/api/reports/${item.id}/file`}
                            download={item.file_name || undefined}
                            title={item.file_name || '다운로드'}
                            onClick={onFileClick}
                          >
                            {item.file_name || '파일'}
                          </a>
                        ) : (
                          '—'
                        )}
                      </td>
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
            <h2>감사 상세</h2>
            <div className="audit-actions">
              <button
                type="button"
                className="run-btn"
                disabled={audit.busy || !detail?.has_file}
                onClick={() => void onReauditSelected()}
              >
                이 건 재감사
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
                  <dt>품질</dt>
                  <dd>
                    {QUALITY_LABEL[detail.quality || 'pending'] || detail.quality}{' '}
                    · scope={detail.quality_scope || '—'} · conf=
                    {formatConfidence(detail.quality_confidence)}
                  </dd>
                </div>
                <div>
                  <dt>감사 시각</dt>
                  <dd>{formatTime(detail.quality_at)}</dd>
                </div>
                <div>
                  <dt>모델</dt>
                  <dd className="mono">{detail.quality_model || '—'}</dd>
                </div>
                <div>
                  <dt>topic</dt>
                  <dd>{String(qj.topic || '—')}</dd>
                </div>
                <div>
                  <dt>framework</dt>
                  <dd>{String(qj.framework_summary || '—')}</dd>
                </div>
                <div>
                  <dt>fail_reasons</dt>
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
                  <dt>pass_signals</dt>
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
                  <dt>rationale</dt>
                  <dd className="audit-rationale">
                    {String(qj.rationale || qj.error || '—')}
                  </dd>
                </div>
              </dl>
            </div>
          ) : null}
        </section>
      ) : null}
    </>
  )
}
