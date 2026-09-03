import type { PeriodPreset } from '../lib/period'
import { formatPeriodLabel, type PeriodRange } from '../lib/period'

const PRESETS: { id: Exclude<PeriodPreset, 'custom'>; label: string }[] = [
  { id: '7d', label: '7일' },
  { id: '30d', label: '30일' },
  { id: '90d', label: '90일' },
]

type Props = {
  preset: PeriodPreset
  range: PeriodRange | null
  customFrom: string
  customTo: string
  loading: boolean
  onPreset: (preset: Exclude<PeriodPreset, 'custom'>) => void
  onCustomFrom: (value: string) => void
  onCustomTo: (value: string) => void
  onApplyCustom: () => void
  onReload: () => void
}

export function PeriodBar({
  preset,
  range,
  customFrom,
  customTo,
  loading,
  onPreset,
  onCustomFrom,
  onCustomTo,
  onApplyCustom,
  onReload,
}: Props) {
  return (
    <div className="period-bar">
      <div className="chip-row" role="group" aria-label="기간 프리셋">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`chip ${preset === p.id ? 'active' : ''}`}
            onClick={() => onPreset(p.id)}
          >
            {p.label}
          </button>
        ))}
        <span className={`chip static ${preset === 'custom' ? 'active' : ''}`}>
          커스텀
        </span>
      </div>

      <div className="period-custom">
        <label>
          <span>부터</span>
          <input
            type="date"
            value={customFrom}
            onChange={(e) => onCustomFrom(e.target.value)}
          />
        </label>
        <label>
          <span>까지</span>
          <input
            type="date"
            value={customTo}
            onChange={(e) => onCustomTo(e.target.value)}
          />
        </label>
        <button type="button" className="btn" onClick={onApplyCustom}>
          적용
        </button>
        <button
          type="button"
          className="btn ghost"
          onClick={onReload}
          disabled={loading || !range}
        >
          새로고침
        </button>
      </div>

      {range ? (
        <p className="period-label">조회 기간: {formatPeriodLabel(range)}</p>
      ) : (
        <p className="period-label warn">유효한 기간을 선택하세요.</p>
      )}
    </div>
  )
}
