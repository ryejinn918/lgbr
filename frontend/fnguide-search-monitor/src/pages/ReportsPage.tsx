import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useReports, type ReportSort } from '../hooks/useReports'
import { useSessionStatus } from '../hooks/useSessionStatus'
import { STATUS_LABEL, formatPublishedAt, formatRelative } from '../lib/format'

const FILTERS = [
  'all',
  'downloaded',
  'blind',
  'listed',
  'no_download',
  'failed',
] as const

export function ReportsPage() {
  const [params, setParams] = useSearchParams()
  const status = params.get('status') || 'all'
  const qParam = params.get('q') || ''
  const sort: ReportSort =
    params.get('sort') === 'page_count' ? 'page_count' : 'published_at'
  const offset = Math.max(0, Number(params.get('offset') || '0') || 0)
  const [qDraft, setQDraft] = useState(qParam)
  const { crawl } = useSessionStatus()
  const crawlBusy =
    crawl.state === 'starting' ||
    crawl.state === 'active' ||
    crawl.state === 'stopping'
  const filtersDirty =
    status !== 'all' || Boolean(qParam) || sort !== 'published_at' || offset > 0

  useEffect(() => {
    setQDraft(qParam)
  }, [qParam])

  const query = useMemo(
    () => ({
      status,
      q: qParam,
      sort,
      limit: 30,
      offset,
      poll: true,
    }),
    [status, qParam, sort, offset],
  )
  const reports = useReports(query)

  function setStatus(next: string) {
    const nextParams = new URLSearchParams(params)
    // 활성 칩을 다시 누르면 전체로 되돌림
    if (!next || next === 'all' || next === status) nextParams.delete('status')
    else nextParams.set('status', next)
    nextParams.delete('offset')
    setParams(nextParams)
  }

  function setSort(next: ReportSort) {
    const nextParams = new URLSearchParams(params)
    // 활성 정렬을 다시 누르면 기본(발행일)으로
    if (next === 'published_at' || next === sort) nextParams.delete('sort')
    else nextParams.set('sort', next)
    nextParams.delete('offset')
    setParams(nextParams)
  }

  function applySearch(e: FormEvent) {
    e.preventDefault()
    const nextParams = new URLSearchParams(params)
    const trimmed = qDraft.trim()
    if (trimmed) nextParams.set('q', trimmed)
    else nextParams.delete('q')
    nextParams.delete('offset')
    setParams(nextParams)
  }

  function resetFilters() {
    setQDraft('')
    setParams(new URLSearchParams())
  }

  function shiftPage(delta: number) {
    const next = Math.max(0, offset + delta * reports.limit)
    const nextParams = new URLSearchParams(params)
    if (next === 0) nextParams.delete('offset')
    else nextParams.set('offset', String(next))
    setParams(nextParams)
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
          {FILTERS.map((key) => (
            <button
              key={key}
              type="button"
              className={`filter-chip${status === key ? ' active' : ''}`}
              onClick={() => setStatus(key)}
            >
              {STATUS_LABEL[key]} {reports.counts[key] ?? 0}
            </button>
          ))}
          <button
            type="button"
            className="filter-chip filter-reset"
            disabled={!filtersDirty}
            onClick={resetFilters}
            title="상태·검색·정렬·페이지 초기화"
          >
            초기화
          </button>
        </div>
        <form className="search-row" onSubmit={applySearch}>
          <input
            type="search"
            placeholder="제목, 증권사, rpt_id"
            value={qDraft}
            onChange={(e) => setQDraft(e.target.value)}
          />
          <button type="submit" className="run-btn">
            검색
          </button>
          {qParam || qDraft ? (
            <button
              type="button"
              className="run-btn"
              onClick={() => {
                setQDraft('')
                const nextParams = new URLSearchParams(params)
                nextParams.delete('q')
                nextParams.delete('offset')
                setParams(nextParams)
              }}
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
                      className={`sort-th${sort === 'published_at' ? ' active' : ''}`}
                      onClick={() => setSort('published_at')}
                      title="발행일 내림차순"
                    >
                      발행일{sort === 'published_at' ? ' ↓' : ''}
                    </button>
                  </th>
                  <th>
                    <button
                      type="button"
                      className={`sort-th${sort === 'page_count' ? ' active' : ''}`}
                      onClick={() => setSort('page_count')}
                      title="페이지수 내림차순"
                    >
                      페이지{sort === 'page_count' ? ' ↓' : ''}
                    </button>
                  </th>
                  <th>rpt_id</th>
                  <th>파일</th>
                  <th title="목록에서 마지막으로 본 시각">최근</th>
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
            disabled={offset <= 0}
            onClick={() => shiftPage(-1)}
          >
            이전
          </button>
          <span className="section-note">
            {offset + 1}–{Math.min(offset + reports.limit, reports.total)} /{' '}
            {reports.total}
          </span>
          <button
            type="button"
            className="run-btn"
            disabled={offset + reports.limit >= reports.total}
            onClick={() => shiftPage(1)}
          >
            다음
          </button>
        </div>
      </section>
    </>
  )
}
