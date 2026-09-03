import { useMemo, useState } from 'react'
import { PeriodBar } from '../components/PeriodBar'
import { SourceSection } from '../components/SourceSection'
import { useMediaBrief } from '../hooks/useMediaBrief'
import {
  rangeFromCustomDates,
  rangeFromPreset,
  toDateInputValue,
  type PeriodPreset,
  type PeriodRange,
} from '../lib/period'
import { MEDIA_SOURCES, SOURCE_LABEL } from '../lib/sources'

function initialCustomFrom(): string {
  const d = new Date()
  d.setDate(d.getDate() - 6)
  return toDateInputValue(d)
}

export function BriefPage() {
  const [preset, setPreset] = useState<PeriodPreset>('7d')
  const [customFrom, setCustomFrom] = useState(initialCustomFrom)
  const [customTo, setCustomTo] = useState(() => toDateInputValue(new Date()))
  const [customRange, setCustomRange] = useState<PeriodRange | null>(null)

  const range = useMemo(() => {
    if (preset === 'custom') return customRange
    return rangeFromPreset(preset)
  }, [preset, customRange])

  const { buckets, loading, error, reload } = useMediaBrief(range)

  function applyPreset(next: Exclude<PeriodPreset, 'custom'>) {
    setPreset(next)
    const r = rangeFromPreset(next)
    setCustomFrom(toDateInputValue(new Date(r.from)))
    const toInclusive = new Date(r.to)
    toInclusive.setDate(toInclusive.getDate() - 1)
    setCustomTo(toDateInputValue(toInclusive))
  }

  function applyCustom() {
    const r = rangeFromCustomDates(customFrom, customTo)
    setCustomRange(r)
    setPreset('custom')
  }

  return (
    <div className="monitor">
      <header className="app-shell">
        <div className="brand-block">
          <p className="brand">Media Brief</p>
          <p className="tagline">기간별 매체 주요 아티클</p>
        </div>
        <PeriodBar
          preset={preset}
          range={range}
          customFrom={customFrom}
          customTo={customTo}
          loading={loading}
          onPreset={applyPreset}
          onCustomFrom={setCustomFrom}
          onCustomTo={setCustomTo}
          onApplyCustom={applyCustom}
          onReload={reload}
        />
      </header>

      <nav className="source-jump" aria-label="매체 바로가기">
        {MEDIA_SOURCES.map((src) => (
          <a key={src} href={`#source-${src}`} className="jump-chip">
            {SOURCE_LABEL[src]}
          </a>
        ))}
      </nav>

      {loading ? <p className="status-line">불러오는 중…</p> : null}
      {error ? <p className="status-line warn">{error}</p> : null}

      <main className="brief-main">
        {buckets.map((bucket) => (
          <SourceSection key={bucket.source} bucket={bucket} />
        ))}
      </main>
    </div>
  )
}
