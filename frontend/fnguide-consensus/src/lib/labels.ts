/** User-facing copy for LG Economic Research Institute operators. */

export const APP_BRAND = '섹터 컨센서스'

export const NAV = {
  compare: '비교',
  frames: '논지',
  ops: '실행',
} as const

/** Frame product views (API kinds stay filled_frame / consensus_frame). */
export const FRAME_TAB = {
  filled: '상세 논지',
  consensus: '골격 논지',
  materials: '근거 리포트',
} as const

export const CHAT_MODE = {
  plain: '일반 답변',
  grounded: '논지 근거 답변',
} as const

/** Compare-column roles: ours = grounded, control = plain. */
export const CHAT_ROLE = {
  ours: '우리',
  control: '대조군',
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
  select: '리포트 선정',
  doc: '리포트 분석',
  consensus: '골격 논지',
  fill: '상세 논지',
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
  excluded: '제외',
}

export function labelStage(stage: string): string {
  return STAGE_LABEL[stage] ?? stage
}

export function labelChatPhase(phase: string): string {
  return CHAT_PHASE[phase] ?? phase
}

export function labelRunState(state: string): string {
  return RUN_STATE[state] ?? state
}

export function labelDocStatus(status: string): string {
  return DOC_STATUS[status] ?? status
}

export function labelRole(role: string): string {
  return ROLE_LABEL[role] ?? role
}
