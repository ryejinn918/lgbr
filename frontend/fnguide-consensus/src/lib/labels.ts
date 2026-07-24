/** User-facing copy for LG Economic Research Institute operators. */

export const APP_BRAND = '섹터 컨센서스'

/** Nav labels; display order in App is compare → frames → select → ops. */
export const NAV = {
  ops: '실행',
  select: '선별',
  frames: '논지',
  compare: '채팅',
} as const

/** Frame product views (API kinds stay filled_frame / consensus_frame). */
export const FRAME_TAB = {
  filled: '살 붙인 논지',
  consensus: '골격',
  materials: '근거 보고서',
} as const

export const CHAT_MODE = {
  plain: '일반 답변',
  grounded: '컨센서스 근거 답변',
} as const

/** Compare-column roles: ours = grounded, control = plain. */
export const CHAT_ROLE = {
  ours: '근거 있음',
  control: '근거 없음',
} as const

export const ROLE_LABEL: Record<string, string> = {
  user: '질문',
  assistant: '답변',
  system: '시스템',
}

export const CHAT_PHASE: Record<string, string> = {
  planning: '계획 중',
  search: '검색 중',
  answer: '작성 중',
}

/** Pipeline stages shown in progress / events. */
export const STAGE_LABEL: Record<string, string> = {
  run: '실행',
  select: '보고서 선별',
  doc: '보고서 요약',
  consensus: '골격',
  fill: '살 붙이기',
}

export const EVENT_LABEL: Record<string, string> = {
  claimed: '시작됨',
  stage_start: '시작',
  stage_end: '끝',
  selected: '선별 완료',
  cache_hit: '요약 재사용',
  cache_miss: '새로 요약',
  compress_done: '요약 완료',
  doc_failed: '요약 실패',
  frame_validated: '골격 완료',
  filled_done: '살 붙이기 완료',
  ended: '완료',
  error: '오류',
}

export const RUN_STATE: Record<string, string> = {
  idle: '대기',
  starting: '시작 중',
  active: '실행 중',
  stopping: '종료 중',
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

export function labelChatPhase(phase: string): string {
  return CHAT_PHASE[phase] ?? phase
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
    state === 'stopping'
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

export function labelRole(role: string): string {
  return ROLE_LABEL[role] ?? role
}
