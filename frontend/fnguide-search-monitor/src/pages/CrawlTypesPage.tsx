import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useCrawlProfiles } from '../hooks/useCrawlProfiles'
import type { CrawlProfile, CrawlProfileMode } from '../types'
import { formatTime } from '../lib/format'
import { PROFILE_MODE_LABEL } from '../lib/themes'

const MODE_LABEL = PROFILE_MODE_LABEL

const SECTOR_OPTIONS = [
  '에너지',
  '소재',
  '산업재',
  '금융',
  'IT',
  '커뮤니케이션서비스',
  '유틸리티',
  '경기소비재',
  '필수소비재',
  '헬스케어',
] as const

const PERIOD_OPTIONS = [3, 6, 12] as const
const PAGE_MIN_OPTIONS = [
  '전체',
  '5p 이상',
  '10p 이상',
  '15p 이상',
  '20p 이상',
  '30p 이상',
] as const

type Draft = {
  keywordsText: string
  sectors: string[]
  period_months: number
  page_min_label: string
}

function keywordsToText(keywords: string[]): string {
  return keywords.join('\n')
}

function textToKeywords(text: string): string[] {
  return text
    .split(/\n|,/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function toDraft(profile: CrawlProfile): Draft {
  return {
    keywordsText: keywordsToText(profile.keywords),
    sectors: [...profile.sectors],
    period_months: profile.period_months,
    page_min_label: profile.page_min_label,
  }
}

function ProfileEditor({
  profile,
  saving,
  onSave,
}: {
  profile: CrawlProfile
  saving: boolean
  onSave: (draft: {
    keywords: string[]
    sectors: string[]
    period_months: number
    page_min_label: string
  }) => Promise<void>
}) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(profile))
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    setDraft(toDraft(profile))
    setDirty(false)
  }, [profile])

  const sectorChoices = useMemo(() => {
    const extra = draft.sectors.filter(
      (s) => !(SECTOR_OPTIONS as readonly string[]).includes(s),
    )
    return [...SECTOR_OPTIONS, ...extra]
  }, [draft.sectors])

  function patch(partial: Partial<Draft>) {
    setDraft((prev) => ({ ...prev, ...partial }))
    setDirty(true)
  }

  function toggleSector(name: string) {
    setDraft((prev) => {
      const has = prev.sectors.includes(name)
      return {
        ...prev,
        sectors: has
          ? prev.sectors.filter((s) => s !== name)
          : [...prev.sectors, name],
      }
    })
    setDirty(true)
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    const keywords = textToKeywords(draft.keywordsText)
    if (keywords.length === 0) {
      window.alert('키워드를 한 줄에 하나씩 입력하세요.')
      return
    }
    await onSave({
      keywords,
      sectors: draft.sectors,
      period_months: draft.period_months,
      page_min_label: draft.page_min_label.trim() || '10p 이상',
    })
    setDirty(false)
  }

  return (
    <form className="panel profile-form" onSubmit={(e) => void submit(e)}>
      <div className="section-head">
        <h2>{MODE_LABEL[profile.mode] ?? profile.mode}</h2>
        <span className="section-note mono">{profile.mode}</span>
      </div>

      <label className="field-block">
        <span>검색 키워드 (한 줄에 하나)</span>
        <textarea
          rows={Math.min(12, Math.max(3, draft.keywordsText.split('\n').length + 1))}
          value={draft.keywordsText}
          onChange={(e) => patch({ keywordsText: e.target.value })}
          disabled={saving}
        />
        <span className="field-hint">
          키워드마다 검색한 뒤, 아래 기간(기본 3개월) 안 결과를 다운로드합니다.
          이미 받은 보고서는 다음 키워드에서 건너뜁니다.
        </span>
      </label>

      <label className="field-block">
        <span>기간</span>
        <select
          value={draft.period_months}
          onChange={(e) => patch({ period_months: Number(e.target.value) })}
          disabled={saving}
        >
          {PERIOD_OPTIONS.map((m) => (
            <option key={m} value={m}>
              {m}개월
            </option>
          ))}
        </select>
      </label>

      <label className="field-block">
        <span>최소 페이지수 (검색 필터)</span>
        <select
          value={draft.page_min_label}
          onChange={(e) => patch({ page_min_label: e.target.value })}
          disabled={saving}
        >
          {!PAGE_MIN_OPTIONS.includes(
            draft.page_min_label as (typeof PAGE_MIN_OPTIONS)[number],
          ) ? (
            <option value={draft.page_min_label}>{draft.page_min_label}</option>
          ) : null}
          {PAGE_MIN_OPTIONS.map((label) => (
            <option key={label} value={label}>
              {label}
            </option>
          ))}
        </select>
        <span className="field-hint">
          Fnguide 목록의 페이지수 필터와 동일합니다. 수집된 보고서 페이지 수는
          리스트의 「페이지」열에 표시됩니다.
        </span>
      </label>

      <fieldset className="sector-fieldset" disabled={saving}>
        <legend>섹터 (비우면 섹터 필터 없음)</legend>
        <div className="sector-grid">
          {sectorChoices.map((name) => (
            <label key={name} className="sector-chip">
              <input
                type="checkbox"
                checked={draft.sectors.includes(name)}
                onChange={() => toggleSector(name)}
              />
              <span>{name}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="actions">
        <button
          type="submit"
          className="run-btn"
          disabled={saving || !dirty}
        >
          {saving ? '저장 중…' : '저장'}
        </button>
        <span className="section-note">
          수정: {formatTime(profile.updated_at)}
        </span>
      </div>
    </form>
  )
}

export function CrawlTypesPage({ embedded = false }: { embedded?: boolean }) {
  const { items, loading, error, saving, refresh, saveProfile } =
    useCrawlProfiles()

  async function onSave(
    mode: CrawlProfileMode,
    draft: {
      keywords: string[]
      sectors: string[]
      period_months: number
      page_min_label: string
    },
  ) {
    try {
      await saveProfile(mode, draft)
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '저장 실패')
    }
  }

  return (
    <>
      {embedded ? (
        <div className="section-head" style={{ marginBottom: '0.75rem' }}>
          <h2>리스트 발굴 타입 · 검색</h2>
          <span className="section-note">
            FnGuide · 리스트 발굴 · 검색 · 프로필만 수정 (생성/삭제 없음)
          </span>
        </div>
      ) : (
        <header className="monitor-header">
          <h1>리스트 발굴 타입 · 검색</h1>
          <p className="lede">
            섹터별 FnGuide 검색 필터 프로파일입니다. 타입 생성/삭제는 없고
            필터만 수정합니다.
          </p>
        </header>
      )}

      {error ? (
        <section className="panel">
          <p className="warn">불러오기 실패: {error}</p>
          <div className="actions">
            <button type="button" className="run-btn" onClick={() => void refresh()}>
              다시 시도
            </button>
          </div>
        </section>
      ) : null}

      {loading && items.length === 0 ? (
        <p className="empty">불러오는 중…</p>
      ) : null}

      {items.map((profile) => (
        <ProfileEditor
          key={profile.mode}
          profile={profile}
          saving={saving === profile.mode}
          onSave={(draft) => onSave(profile.mode, draft)}
        />
      ))}

      {!loading && !error && items.length === 0 ? (
        <p className="empty">프로파일이 없습니다. 마이그레이션을 확인하세요.</p>
      ) : null}
    </>
  )
}
