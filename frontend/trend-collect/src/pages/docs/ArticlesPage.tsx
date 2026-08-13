import { useMemo, useState, type MouseEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
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

function parseSourceParam(raw: string | null): string {
  if (raw && (SOURCE_FILTERS as readonly string[]).includes(raw)) return raw
  return 'all'
}

/** Nikkei stores Korean summary in body_text; ARG stores raw body. */
function isSummaryBody(item: NewsArticleRecord): boolean {
  if (item.source === 'nikkei') return true
  const summarized = item.attrs?.summarized_at
  return typeof summarized === 'string' && summarized.trim() !== ''
}

function contentFieldLabel(item: NewsArticleRecord): string {
  return isSummaryBody(item) ? '요약' : '본문'
}

function articleBodyText(item: NewsArticleRecord): string {
  return (item.body_text ?? '').trim()
}

type BodyStatus = {
  label: string
  statusClass: 'downloaded' | 'listed' | 'failed'
}

function bodyStatus(item: NewsArticleRecord): BodyStatus {
  const hasBody = Boolean(item.has_body) || Boolean(articleBodyText(item))
  if (hasBody) {
    return { label: '수집됨', statusClass: 'downloaded' }
  }
  if (item.body_fetch_error?.trim()) {
    return { label: '본문실패', statusClass: 'failed' }
  }
  return { label: '본문없음', statusClass: 'listed' }
}

export function ArticlesPage() {
  const [params, setParams] = useSearchParams()
  const [qDraft, setQDraft] = useState('')
  const [q, setQ] = useState('')
  const source = parseSourceParam(params.get('source'))
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

  function commitSource(next: string) {
    const nextParams = new URLSearchParams(params)
    if (next === 'all') nextParams.delete('source')
    else nextParams.set('source', next)
    setParams(nextParams)
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
  const selectedBody = selected ? articleBodyText(selected) : ''
  const selectedBodyError = selected?.body_fetch_error?.trim() || ''

  return (
    <>
      <div className="section-head" style={{ marginBottom: '0.75rem' }}>
        <h2>기사 통합</h2>
        <p className="section-note">
          메타와 요약을 모읍니다. 원문은 요약에만 쓰고 남기지 않습니다 ·{' '}
          <Link to="/collect/arg/list/feed">ARG 피드</Link>
          {' · '}
          <Link to="/collect/nikkei/list/feed">Nikkei 피드</Link>
          {' · '}
          <Link to="/collect/nikkei/body/fetch">Nikkei 본문</Link>
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

        <div
          className={`report-workspace${selectedId ? ' has-detail' : ''}`}
        >
          <div className="report-sheet">
            <table className="report-table">
              <thead>
                <tr>
                  <th className="col-status">본문</th>
                  <th className="col-title">제목</th>
                  <th className="col-provider">섹션</th>
                  <th className="col-published">발행</th>
                  <th className="col-source">매체</th>
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
                    const originalUrl = articlePublicOriginalUrl(item.url)
                    const displayTitle =
                      (item.title_ko && item.title_ko.trim()) || item.title
                    const showOriginal =
                      Boolean(item.title_ko && item.title_ko.trim()) &&
                      item.title_ko !== item.title
                    const status = bodyStatus(item)
                    return (
                      <tr
                        key={item.id}
                        className={selectedRow ? 'row-selected' : undefined}
                        onClick={() => onRowClick(item.id)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td className="col-status">
                          <span
                            className={`status-pill status-${status.statusClass}`}
                            title={item.body_fetch_error || undefined}
                          >
                            {status.label}
                          </span>
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
                        <td className="col-provider">
                          {item.section || item.publisher || '—'}
                        </td>
                        <td className="col-published mono">
                          {formatPublishedAt(item.published_at)}
                        </td>
                        <td className="col-source">
                          {SOURCE_LABEL[item.source] || item.source}
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

          {selectedId ? (
            <div className="report-audit-detail">
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
                    <div className="details-span">
                      <dt>제목</dt>
                      <dd>
                        {(selected.title_ko && selected.title_ko.trim()) ||
                          selected.title}
                        {selected.title_ko &&
                        selected.title_ko.trim() &&
                        selected.title_ko !== selected.title ? (
                          <div
                            className="section-note"
                            style={{ marginTop: 4 }}
                          >
                            원문: {selected.title}
                          </div>
                        ) : null}
                      </dd>
                    </div>
                    <div>
                      <dt>매체</dt>
                      <dd>
                        {SOURCE_LABEL[selected.source] || selected.source}
                      </dd>
                    </div>
                    <div>
                      <dt>섹션</dt>
                      <dd>
                        {selected.section || selected.publisher || '—'}
                      </dd>
                    </div>
                    <div>
                      <dt>발행</dt>
                      <dd>{formatTime(selected.published_at)}</dd>
                    </div>
                    <div>
                      <dt>최근 확인</dt>
                      <dd>{formatTime(selected.last_seen_at)}</dd>
                    </div>
                    {selected.body_fetched_at ? (
                      <div>
                        <dt>
                          {isSummaryBody(selected)
                            ? '요약 시각'
                            : '본문 수집'}
                        </dt>
                        <dd>{formatTime(selected.body_fetched_at)}</dd>
                      </div>
                    ) : null}
                    <div>
                      <dt>최초 발견</dt>
                      <dd>{formatTime(selected.first_seen_at)}</dd>
                    </div>
                    <div className="details-span">
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
                    <div className="details-span">
                      <dt>키</dt>
                      <dd className="mono">{selected.source_key}</dd>
                    </div>
                    <div className="details-span">
                      <dt>{contentFieldLabel(selected)}</dt>
                      <dd className="audit-rationale">
                        {selectedBody ? (
                          selectedBody
                        ) : selectedBodyError ? (
                          <span className="warn">{selectedBodyError}</span>
                        ) : (
                          <>
                            아직 {contentFieldLabel(selected)}이 없습니다.
                            {selected.source === 'nikkei' ? (
                              <>
                                {' '}
                                <Link to="/collect/nikkei/body/fetch">
                                  Nikkei 본문 수집
                                </Link>
                                을 실행하세요.
                              </>
                            ) : null}
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
                          </>
                        )}
                      </dd>
                    </div>
                  </dl>
                </div>
              ) : null}
            </div>
          ) : null}
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
    </>
  )
}
