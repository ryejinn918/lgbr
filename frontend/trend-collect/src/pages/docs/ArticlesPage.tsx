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
  arg: 'ARG',
}

const BODY_FILTERS: NewsArticleBodyFilter[] = ['all', 'yes', 'no']

const BODY_LABEL: Record<NewsArticleBodyFilter, string> = {
  all: '전체',
  yes: '수집됨',
  no: '미수집',
}

export function ArticlesPage() {
  const [qDraft, setQDraft] = useState('')
  const [q, setQ] = useState('')
  const [hasBody, setHasBody] = useState<NewsArticleBodyFilter>('all')
  const [offset, setOffset] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const limit = 30
  const articles = useNewsArticles({
    source: 'all',
    q,
    hasBody,
    limit,
    offset,
  })

  const selected: NewsArticleRecord | null = useMemo(() => {
    if (!selectedId) return null
    return articles.items.find((item) => item.id === selectedId) ?? null
  }, [articles.items, selectedId])

  const dirty = hasBody !== 'all' || q !== '' || qDraft !== ''

  function commitBody(next: NewsArticleBodyFilter) {
    setHasBody(next)
    setOffset(0)
    setSelectedId(null)
  }

  function resetFilters() {
    setHasBody('all')
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
          매체 공통 기사 리스트 ·{' '}
          <Link to="/collect/arg/list/feed">ARG 피드</Link>
          {' · '}
          <Link to="/collect/arg/body/fetch">ARG 본문</Link>
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
          <h2>전체 매체</h2>
          <p className="section-note">
            {articles.fetchError
              ? articles.fetchError
              : articles.loading
                ? '불러오는 중…'
                : `${articles.total}건`}
          </p>
        </div>

        <div className="filter-row">
          {BODY_FILTERS.map((key) => (
            <button
              key={key}
              type="button"
              className={`filter-chip${hasBody === key ? ' active' : ''}`}
              onClick={() => commitBody(key)}
            >
              {BODY_LABEL[key]} {articles.bodyCounts[key] ?? 0}
            </button>
          ))}
          <button
            type="button"
            className="filter-chip filter-reset"
            disabled={!dirty}
            onClick={resetFilters}
            title="본문 필터·검색·페이지 초기화"
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
                <th className="col-status">본문</th>
                <th className="col-seen">최근</th>
              </tr>
            </thead>
            <tbody>
              {articles.items.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    {articles.loading
                      ? '불러오는 중…'
                      : '아직 기사가 없습니다. 수집에서 리스트 발굴을 실행하세요.'}
                  </td>
                </tr>
              ) : (
                articles.items.map((item) => {
                  const selectedRow = selectedId === item.id
                  const hasBody = Boolean(item.has_body)
                  const originalUrl = articlePublicOriginalUrl(item.url)
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
                      <td className="col-title report-title" title={item.title}>
                        {originalUrl ? (
                          <a
                            className="report-file-link"
                            href={originalUrl}
                            target="_blank"
                            rel="noreferrer"
                            onClick={onLinkClick}
                          >
                            {item.title}
                          </a>
                        ) : (
                          item.title
                        )}
                      </td>
                      <td className="col-status">
                        <span
                          className={`status-pill status-${hasBody ? 'downloaded' : 'listed'}`}
                          title={
                            hasBody
                              ? undefined
                              : item.body_fetch_error || undefined
                          }
                        >
                          {hasBody ? '수집됨' : '미수집'}
                        </span>
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
                  <dd>{selected.title}</dd>
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
                  <dt>본문</dt>
                  <dd>
                    {selected.has_body && selected.body_text ? (
                      <pre
                        style={{
                          whiteSpace: 'pre-wrap',
                          margin: 0,
                          fontFamily: 'inherit',
                        }}
                      >
                        {selected.body_text}
                      </pre>
                    ) : selected.body_fetch_error ? (
                      <>
                        본문 채우기 실패:{' '}
                        {selected.body_fetch_error}
                        {' · '}
                        <Link to="/collect/arg/body/fetch">다시 시도</Link>
                      </>
                    ) : (
                      <>
                        본문을 아직 수집하지 않았습니다.{' '}
                        <Link to="/collect/arg/body/fetch">본문 채우기</Link>
                        로 가져오거나 원문 링크로 확인하세요.
                      </>
                    )}
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
