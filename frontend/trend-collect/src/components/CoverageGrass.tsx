import type { ReactNode } from 'react'
import type { CoverageSourceRow } from '../types'

function intensity(count: number, max: number): number {
  if (count <= 0 || max <= 0) return 0
  const ratio = count / max
  if (ratio <= 0.2) return 1
  if (ratio <= 0.4) return 2
  if (ratio <= 0.7) return 3
  return 4
}

function formatWeekLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  return `${d.getMonth() + 1}/${d.getDate()}`
}

export function CoverageGrass({
  weeks,
  sources,
  error,
  loading,
}: {
  weeks: string[]
  sources: CoverageSourceRow[]
  error: string | null
  loading: boolean
}) {
  if (error) return <p className="warn">{error}</p>
  if (loading && weeks.length === 0) {
    return <p className="empty">불러오는 중…</p>
  }
  if (weeks.length === 0) {
    return <p className="empty">표시할 주가 없습니다.</p>
  }

  const labelEvery = weeks.length > 10 ? 2 : 1

  const cells: ReactNode[] = sources.flatMap((row) => {
    const rowMax = Math.max(0, ...row.counts)
    const rowTotal = row.counts.reduce((sum, n) => sum + n, 0)
    return [
      <div
        key={`${row.id}-label`}
        className="coverage-source-label"
        title={`${row.label} · 표시 기간 ${rowTotal}건`}
      >
        <span className="coverage-source-name">{row.label}</span>
        <span className="coverage-source-total">{rowTotal}건</span>
      </div>,
      ...weeks.map((week, i) => {
        const count = row.counts[i] ?? 0
        const level = intensity(count, rowMax)
        const summary = `${row.label} · ${week} · ${count}건`
        return (
          <div
            key={`${row.id}-${week}`}
            className={`coverage-cell level-${level}`}
            title={summary}
            aria-label={summary}
          >
            {count > 0 ? count : ''}
          </div>
        )
      }),
    ]
  })

  return (
    <div className="coverage-grass">
      <div
        className="coverage-grid"
        style={{
          gridTemplateColumns: `6rem repeat(${weeks.length}, minmax(0, 1fr))`,
        }}
      >
        <div className="coverage-corner" aria-hidden />
        {weeks.map((week, i) => (
          <div
            key={week}
            className="coverage-week-label mono"
            title={`주 시작 ${week}`}
          >
            {i % labelEvery === 0 || i === weeks.length - 1
              ? formatWeekLabel(week)
              : ''}
          </div>
        ))}
        {cells}
      </div>
      <div className="coverage-legend">
        <span className="section-note">적음</span>
        {[0, 1, 2, 3, 4].map((level) => (
          <span
            key={level}
            className={`coverage-cell level-${level} legend`}
            aria-hidden
          />
        ))}
        <span className="section-note">많음</span>
      </div>
    </div>
  )
}
