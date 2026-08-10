import { useMemo, useState, type MouseEvent } from 'react'
import { Link } from 'react-router-dom'
import { useNewsArticles } from '../../hooks/useNewsArticles'
import type {
  NewsArticleBodyFilter,
  NewsArticleRecord,
} from '../../types'
import {
  formatPublishedAt,
  formatRelative,
  formatTime,
} from '../../lib/format'
import { articlePublicOriginalUrl } from '../../lib/publicOriginalUrl'

const SOURCE_LABEL: Record<string, string> = {
  all: '전체',
  arg: 'ARG',
  google_news: 'Google News',
  nikkei: 'Nikkei',
}

/** Chip order for media filter (must match API OTHER_MEDIA_SOURCES). */
const SOURCE_FILTERS = ['all', 'arg', 'google_news', 'nikkei'] as const

export function ArticlesPage() {
  const [qDraft, setQDraft] = useState('')
  const [q, setQ] = useState('')
  const [source, setSource] = useState<string>('all')
  const [offset, setOffset] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const limit = 30
  const hasBody: NewsArticleBodyFilter = 'all'
  const articles = useNewsArticles({
    source,
    q,
    hasBody,
    limit,
    offset,
  })

  const selected: NewsArticleRecord | null = useMemo(() => {
    if (!selectedId) return null
    return articles.items.find((item) => item.id === selectedId) ?? null
  }, [articles.items, selectedId])

  const dirty = source !== 'all' || q !== '' || qDraft !== ''

  function commitSource(next: string) {
    setSource(next)
    setOffset(0)
    setSelectedId(null)
  }

  function resetFilters() {
    setSource('all')
    setQ('')
    setQDraft('')
    setOffset(0)
    setSelectedId(null)
  }

  function onRowClick(id: string) {
    setSelectedId((prev) => (prev === id ? null : id))
  }

  function onLinkClick(e: MouseEvent) {
    e.stopPropagation()
  }

  const selectedOriginalUrl = articlePublicOriginalUrl(selected?.url)

  return (
    <>
      <div className="section-head" style={{ marginBottom: '0.75rem' }}>
        <h2>기사 통합</h2>
        <p className="section-note">
          메타만 모읍니다. 원문은 남기지 않습니다 ·{' '}
          <Link to="/collect/arg/list/feed">ARG 피드</Link>
        </p>
      </div>

      <form
        className="search-row"
        onSubmit={(e) => {
          e.preventDefault()
          setOffset(0)
          setSelectedId(null)
          setQ(qDraft)
        }}
      >
        <input
          type="search"
          placeholder="제목·URL 검색"
          value={qDraft}
          onChange={(e) => setQDraft(e.target.value)}
        />
        <button type="submit">검색</button>
      </form>

      <section className="panel">
        <div className="section-head">
          <h2>{SOURCE_LABEL[source] ?? source}</h2>
          <p className="section-note">
            {articles.fetchError
              ? articles.fetchError
              : articles.loading
                ? '불러오는 중…'
                : `${articles.total}건`}
          </p>
        </div>

        <div className="filter-row" aria-label="매체 필터">
          {SOURCE_FILTERS.map((key) => (
            <button
              key={key}
              type="button"
              className={`filter-chip${source === key ? ' active' : ''}`}
              onClick={() => commitSource(key)}
            >
              {SOURCE_LABEL[key]} {articles.sourceCounts[key] ?? 0}
            </button>
          ))}
        </div>

        <div className="filter-row" aria-label="필터 초기화">
          <button
            type="button"
            className="filter-chip filter-reset"
            disabled={!dirty}
            onClick={resetFilters}
            title="매체 필터·검색·페이지 초기화"
          >
            초기화
          </button>
        </div>

        <div className="report-sheet">
          <table className="report-table">
            <thead>
              <tr>
                <th className="col-provider">매체</th>
                <th className="col-published">발행</th>
                <th className="col-provider">섹션</th>
                <th className="col-title">제목</th>
                <th className="col-seen">최근</th>
              </tr>
            </thead>
            <tbody>
              {articles.items.length === 0 ? (
                <tr>
                  <td colSpan={5}>
                    {articles.loading
                      ? '불러오는 중…'
                      : '아직 기사가 없습니다. 수집에서 리스트 발굴을 실행하세요.'}
                  </td>
                </tr>
              ) : (
                articles.items.map((item) => {
                  const selectedRow = selectedId === item.id
                  const originalUrl = articlePublicOriginalUrl(item.url)
                  const displayTitle =
                    (item.title_ko && item.title_ko.trim()) || item.title
                  const showOriginal =
                    Boolean(item.title_ko && item.title_ko.trim()) &&
                    item.title_ko !== item.title
                  return (
                    <tr
                      key={item.id}
                      className={selectedRow ? 'row-selected' : undefined}
                      onClick={() => onRowClick(item.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="col-provider">
                        {SOURCE_LABEL[item.source] || item.source}
                      </td>
                      <td className="col-published mono">
                        {formatPublishedAt(item.published_at)}
                      </td>
                      <td className="col-provider">
                        {item.section || item.publisher || '—'}
                      </td>
                      <td className="col-title report-title">
                        <div className="report-title-inner">
                          <span
                            className="report-title-text"
                            title={
                              showOriginal
                                ? `${displayTitle} / ${item.title}`
                                : item.title
                            }
                          >
                            {displayTitle}
                          </span>
                          {showOriginal ? (
                            <span
                              className="section-note"
                              style={{ display: 'block', marginTop: 2 }}
                            >
                              {item.title}
                            </span>
                          ) : null}
                          {originalUrl ? (
                            <a
                              className="report-file-link report-original-link"
                              href={originalUrl}
                              target="_blank"
                              rel="noreferrer"
                              title="원문 사이트(저장본 아님)"
                              onClick={onLinkClick}
                            >
                              원문
                            </a>
                          ) : null}
                        </div>
                      </td>
                      <td
                        className="col-seen"
                        title={item.last_seen_at || undefined}
                      >
                        {formatRelative(item.last_seen_at)}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="pager">
          <button
            type="button"
            className="run-btn"
            disabled={offset <= 0}
            onClick={() => {
              setSelectedId(null)
              setOffset(Math.max(0, offset - limit))
            }}
          >
            이전
          </button>
          <span className="section-note">
            {offset + 1}–{Math.min(offset + limit, articles.total)} /{' '}
            {articles.total}
          </span>
          <button
            type="button"
            className="run-btn"
            disabled={offset + limit >= articles.total}
            onClick={() => {
              setSelectedId(null)
              setOffset(offset + limit)
            }}
          >
            다음
          </button>
        </div>
      </section>

      {selectedId ? (
        <section className="panel audit-detail">
          <div className="section-head">
            <h2>기사 상세</h2>
            <div className="audit-actions">
              {selectedOriginalUrl ? (
                <a
                  className="run-btn"
                  href={selectedOriginalUrl}
                  target="_blank"
                  rel="noreferrer"
                  onClick={onLinkClick}
                >
                  원문 열기
                </a>
              ) : null}
              <button
                type="button"
                className="run-btn"
                onClick={() => setSelectedId(null)}
              >
                닫기
              </button>
            </div>
          </div>
          {!selected && articles.loading ? (
            <p className="empty">불러오는 중…</p>
          ) : null}
          {!selected && !articles.loading ? (
            <p className="warn">선택한 항목이 현재 페이지에 없습니다.</p>
          ) : null}
          {selected ? (
            <div className="details">
              <dl>
                <div>
                  <dt>매체</dt>
                  <dd>{SOURCE_LABEL[selected.source] || selected.source}</dd>
                </div>
                <div>
                  <dt>제목</dt>
                  <dd>
                    {(selected.title_ko && selected.title_ko.trim()) ||
                      selected.title}
                    {selected.title_ko &&
                    selected.title_ko.trim() &&
                    selected.title_ko !== selected.title ? (
                      <div className="section-note" style={{ marginTop: 4 }}>
                        원문: {selected.title}
                      </div>
                    ) : null}
                  </dd>
                </div>
                <div>
                  <dt>섹션</dt>
                  <dd>{selected.section || selected.publisher || '—'}</dd>
                </div>
                <div>
                  <dt>발행</dt>
                  <dd>{formatTime(selected.published_at)}</dd>
                </div>
                <div>
                  <dt>키</dt>
                  <dd className="mono">{selected.source_key}</dd>
                </div>
                <div>
                  <dt>URL</dt>
                  <dd>
                    <a
                      href={selected.url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={onLinkClick}
                    >
                      {selected.url}
                    </a>
                  </dd>
                </div>
                <div>
                  <dt>최초 발견</dt>
                  <dd>{formatTime(selected.first_seen_at)}</dd>
                </div>
                <div>
                  <dt>최근 확인</dt>
                  <dd>{formatTime(selected.last_seen_at)}</dd>
                </div>
                <div>
                  <dt>원문</dt>
                  <dd>
                    원문은 요약에만 쓰고 남기지 않습니다. 화면에는 메타만
                    보입니다.
                    {selectedOriginalUrl ? (
                      <>
                        {' '}
                        <a
                          href={selectedOriginalUrl}
                          target="_blank"
                          rel="noreferrer"
                          title="원문 사이트(저장본 아님)"
                          onClick={onLinkClick}
                        >
                          원문 사이트에서 확인
                        </a>
                      </>
                    ) : null}
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
