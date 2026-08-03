/** User-facing copy for LG Economic Research Institute operators. */

import type { ConsensusTheme } from '../types'
import { THEME_LABEL } from '../types'

export const APP_BRAND = '섹터 컨센서스'

/** e.g. AI → "AI 섹터" (avoid bare "AI 실행 중"). */
export function labelThemeSector(theme: ConsensusTheme | string): string {
  const name = THEME_LABEL[theme as ConsensusTheme] ?? theme
  return `${name} 섹터`
}

/** Content theme id → short Korean label (unknown ids pass through). */
export function labelTheme(theme: string | null | undefined): string {
  if (!theme) return '—'
  return THEME_LABEL[theme as ConsensusTheme] ?? theme
}

export function labelThemes(themes: string[] | null | undefined): string {
  if (!themes?.length) return '—'
  if (themes.length === 1) return labelTheme(themes[0])
  const [primary, ...rest] = themes
  return `${labelTheme(primary)} · ${rest.map(labelTheme).join(', ')}`
}

/** Nav labels; display order: axes → frames → eval. */
export const NAV = {
  axes: '분석 축',
  frames: '컨센서스',
  eval: '평가',
} as const

/** Frame product views (API kinds stay filled_frame / consensus_frame). */
export const FRAME_TAB = {
  filled: '보고서',
  consensus: '개요',
  materials: '근거 보고서',
} as const

/** Pipeline stages shown in progress / events. */
export const STAGE_LABEL: Record<string, string> = {
  run: '실행',
  thesis: '분석 축 잡기',
  select: '보고서 선별',
  doc: '보고서 요약',
  consensus: '개요',
  fill: '보고서',
}

export const EVENT_LABEL: Record<string, string> = {
  claimed: '시작됨',
  stage_start: '시작',
  stage_end: '끝',
  cut_done: '분석 축 확정',
  awaiting: '분석 축 확인 대기',
  selected: '선별 완료',
  cache_hit: '요약 재사용',
  cache_miss: '새로 요약',
  compress_done: '요약 완료',
  doc_failed: '요약 실패',
  frame_validated: '개요 완료',
  filled_done: '보고서 완료',
  ended: '완료',
  error: '오류',
}

export const RUN_STATE: Record<string, string> = {
  idle: '대기',
  starting: '시작 중',
  active: '실행 중',
  stopping: '종료 중',
  awaiting: '분석 축 확인 대기',
  ended: '완료',
  error: '오류',
}

export const DOC_STATUS: Record<string, string> = {
  pending: '대기',
  cache_hit: '요약 재사용',
  ok: '완료',
  error: '오류',
  failed: '실패',
  excluded: '제외',
}

export function labelStage(stage: string): string {
  return STAGE_LABEL[stage] ?? stage
}

export function labelEvent(event: string): string {
  return EVENT_LABEL[event] ?? event
}

export function labelRunState(state: string): string {
  return RUN_STATE[state] ?? state
}

/** Newest-first history index → operator-facing run label (no asset ids). */
export function labelRunSlot(
  index: number,
  state: string | null | undefined,
): string {
  if (
    state === 'starting' ||
    state === 'active' ||
    state === 'stopping' ||
    state === 'awaiting'
  ) {
    return '현재 실행'
  }
  if (index <= 0) return '최근 실행'
  if (index === 1) return '이전 실행'
  return `이전 실행 (${index})`
}

export function labelDocStatus(status: string): string {
  return DOC_STATUS[status] ?? status
}

/** !can_start — start / continue CTAs blocked by another open run */
export const BLOCKED_BY_OPEN_RUN =
  '다른 분석이 진행 중이라 지금은 할 수 없습니다.'

/** This sector already has a live open run (axes start CTA) */
export const BLOCKED_BY_THIS_SECTOR =
  '이미 이 섹터 분석이 진행 중입니다.'
