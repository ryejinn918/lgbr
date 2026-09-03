import { SOURCE_LABEL } from '../lib/sources'
import type { SourceBucket } from '../hooks/useMediaBrief'
import { ArticleCard } from './ArticleCard'

type Props = {
  bucket: SourceBucket
}

export function SourceSection({ bucket }: Props) {
  const label = SOURCE_LABEL[bucket.source]
  return (
    <section className="source-section" id={`source-${bucket.source}`}>
      <header className="source-head">
        <h2>{label}</h2>
        <span className="source-count">
          {bucket.error
            ? '오류'
            : bucket.total > 0
              ? `${bucket.items.length} / ${bucket.total}건`
              : '0건'}
        </span>
      </header>
      {bucket.error ? (
        <p className="empty warn">{bucket.error}</p>
      ) : bucket.items.length === 0 ? (
        <p className="empty">이 기간에 수집된 아티클이 없습니다.</p>
      ) : (
        <div className="article-grid">
          {bucket.items.map((item) => (
            <ArticleCard key={`${item.lane}-${item.id}`} article={item} />
          ))}
        </div>
      )}
    </section>
  )
}
