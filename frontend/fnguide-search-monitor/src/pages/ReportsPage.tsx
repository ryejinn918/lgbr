import { useMemo, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useReports } from '../hooks/useReports'
import { useSessionStatus } from '../hooks/useSessionStatus'
import { STATUS_LABEL, formatRelative } from '../lib/format'

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
  const offset = Math.max(0, Number(params.get('offset') || '0') || 0)
  const [qDraft, setQDraft] = useState(qParam)
  const { crawl } = useSessionStatus()
  const crawlBusy =
    crawl.state === 'starting' ||
    crawl.state === 'active' ||
    crawl.state === 'stopping'

  const query = useMemo(
    () => ({
      status,
      q: qParam,
      limit: 30,
      offset,
      poll: true,
    }),
    [status, qParam, offset],
  )
  const reports = useReports(query)

  function setStatus(next: string) {
    const nextParams = new URLSearchParams(params)
    if (!next || next === 'all') nextParams.delete('status')
    else nextParams.set('status', next)
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
        </div>
        <form className="search-row" onSubmit={applySearch}>
          <input
            type="search"
            placeholder="제목 또는 rpt_id"
            value={qDraft}
            onChange={(e) => setQDraft(e.target.value)}
          />
          <button type="submit" className="run-btn">
            검색
          </button>
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
          <ul className="report-list">
            {reports.items.map((item) => (
              <li key={item.id}>
                <span className={`status-pill status-${item.status}`}>
                  {STATUS_LABEL[item.status] || item.status}
                </span>
                <span className="report-title">{item.title}</span>
                <span className="report-side">
                  <span className="mono">{item.source_key}</span>
                  <span>{item.has_file ? item.file_name || '파일' : '—'}</span>
                  <span>{formatRelative(item.last_seen_at)}</span>
                </span>
              </li>
            ))}
          </ul>
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
