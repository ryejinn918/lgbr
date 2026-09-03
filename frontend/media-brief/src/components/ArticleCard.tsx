import { formatPublishedAt, truncate } from '../lib/format'
import type { BriefArticle } from '../types'

type Props = {
  article: BriefArticle
}

export function ArticleCard({ article }: Props) {
  const title = (
    <>
      <span className="article-title">{article.title}</span>
      {article.titleKo ? (
        <span className="article-title-ko">{article.titleKo}</span>
      ) : null}
    </>
  )

  return (
    <article className="article-card">
      <div className="article-meta">
        <time dateTime={article.publishedAt ?? undefined}>
          {formatPublishedAt(article.publishedAt)}
        </time>
        {article.section ? (
          <span className="article-section">{article.section}</span>
        ) : null}
      </div>
      {article.url ? (
        <a
          className="article-link"
          href={article.url}
          target="_blank"
          rel="noreferrer"
        >
          {title}
        </a>
      ) : (
        <div className="article-link muted">{title}</div>
      )}
      {article.snippet ? (
        <p className="article-snippet">{truncate(article.snippet)}</p>
      ) : null}
    </article>
  )
}
