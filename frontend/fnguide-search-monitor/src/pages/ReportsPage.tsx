import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useReports } from '../hooks/useReports'
import { useSessionStatus } from '../hooks/useSessionStatus'
import { STATUS_LABEL, formatPublishedAt, formatRelative } from '../lib/format'
import {
  STATUS_FILTERS,
  isReportFiltersDirty,
  parseReportFilters,
  resetReportFilters,
  resolveReportSort,
  serializeReportFilters,
  withPage,
  withQuery,
  withSort,
  withStatus,
  type ReportFilters,
} from '../lib/reportFilters'

export function ReportsPage() {
  const [params, setParams] = useSearchParams()
  const searchKey = params.toString()
  const filters = useMemo(
    () => parseReportFilters(new URLSearchParams(searchKey)),
    [searchKey],
  )
  const [qDraft, setQDraft] = useState(filters.q)
  const { crawl } = useSessionStatus()
  const crawlBusy =
    crawl.state === 'starting' ||
    crawl.state === 'active' ||
    crawl.state === 'stopping'
  const dirty = isReportFiltersDirty(filters, qDraft)

  useEffect(() => {
    setQDraft(filters.q)
  }, [filters.q])

  const query = useMemo(
    () => ({
      status: filters.status,
      q: filters.q,
      sort: resolveReportSort(filters.sort),
      limit: 30,
      offset: filters.offset,
      poll: true,
    }),
    [filters],
  )
  const reports = useReports(query)

  function commit(next: ReportFilters) {
    setQDraft(next.q)
    const serialized = serializeReportFilters(next)
    // 빈 쿼리는 객체로 넘겨 RR가 search를 확실히 지우게 함
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

  return (
    <>
      <header className="monitor-header">
        <h1>보고서</h1>
        <p className="lede">리스트·다운로드 상태가 기록된 전체 카탈로그입니다.</p>
      </header>

      {crawlBusy && crawl.crawl ? (
        <p className="panel live-banner">
          수집 중: {crawl.crawl.mode}
          {crawl.crawl.asset_id ? ` · ${crawl.crawl.asset_id}` : ''}
          {' · '}
          <Link to="/">대시보드에서 보기</Link>
        </p>
      ) : null}

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
            title="상태·검색·정렬·페이지 초기화"
          >
            초기화
          </button>
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
            <table className="report-table">
              <thead>
                <tr>
                  <th>상태</th>
                  <th>제목</th>
                  <th>증권사</th>
                  <th>
                    <button
                      type="button"
                      className={`sort-th${filters.sort === 'published_at' ? ' active' : ''}`}
                      onClick={() => commit(withSort(filters, 'published_at'))}
                      title="발행일 내림차순 (다시 누르면 해제)"
                    >
                      발행일{filters.sort === 'published_at' ? ' ↓' : ''}
                    </button>
                  </th>
                  <th>
                    <button
                      type="button"
                      className={`sort-th${filters.sort === 'page_count' ? ' active' : ''}`}
                      onClick={() => commit(withSort(filters, 'page_count'))}
                      title="페이지수 내림차순 (다시 누르면 해제)"
                    >
                      페이지{filters.sort === 'page_count' ? ' ↓' : ''}
                    </button>
                  </th>
                  <th>rpt_id</th>
                  <th>파일</th>
                  <th>
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
                {reports.items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <span className={`status-pill status-${item.status}`}>
                        {STATUS_LABEL[item.status] || item.status}
                      </span>
                    </td>
                    <td className="report-title">{item.title}</td>
                    <td>{item.provider || '—'}</td>
                    <td className="mono">
                      {formatPublishedAt(item.published_at)}
                    </td>
                    <td className="mono report-pages">
                      {item.page_count != null ? item.page_count : '—'}
                    </td>
                    <td className="mono">{item.source_key}</td>
                    <td className="report-file">
                      {item.has_file ? (
                        <a
                          className="report-file-link"
                          href={`/api/reports/${item.id}/file`}
                          download={item.file_name || undefined}
                          title={item.file_name || '다운로드'}
                        >
                          {item.file_name || '파일'}
                        </a>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td title={item.last_seen_at || undefined}>
                      {formatRelative(item.last_seen_at)}
                    </td>
                  </tr>
                ))}
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
    </>
  )
}
