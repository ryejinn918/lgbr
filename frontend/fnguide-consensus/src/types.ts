export type ConsensusTheme =
  | 'datacenter'
  | 'ai'
  | 'physical_ai'
  | 'appliance'
  | 'display'
  | 'automotive'
  | 'petrochemical'

export type ConsensusState =
  | 'idle'
  | 'starting'
  | 'active'
  | 'stopping'
  | 'awaiting'
  | 'ended'
  | 'error'

/** Pack / axis review stored on consensus_runs.criteria. */
export type SelectCriteria = {
  select?: string
  until?: string | null
  resume_from?: 'select' | 'doc' | null
  thesis?: string | null
  cut_logic?: string | null
  coverage_notes?: string | null
  pillar_sketch?: string[] | null
  core_count?: number
  bibliography_count?: number
  core_max?: number
  quality_pass_count?: number
  pool_count?: number
}

export type ConsensusRun = {
  id: string
  asset_id: string
  theme: ConsensusTheme
  question: string
  model: string
  state: ConsensusState
  label: string
  progress: Record<string, unknown>
  criteria?: SelectCriteria | null
  message?: string | null
  pid?: number | null
  started_at?: string | null
  ended_at?: string | null
  created_at?: string | null
}

export type RunDoc = {
  role: string
  rank: number | null
  doc_status: string
  report_id: string
  title: string
  provider?: string | null
  page_count?: number | null
  select_why?: string | null
  exclude_reason?: string | null
}

export type ConsensusEvent = {
  id: string
  run_id: string
  at: string | null
  level: string
  stage: string
  event: string
  detail: Record<string, unknown>
}

export type ConsensusStatusResponse = {
  ok: boolean
  label: string
  state: ConsensusState
  run: ConsensusRun | null
  progress: Record<string, unknown>
  events: ConsensusEvent[]
  can_start: boolean
  message?: string | null
}

export type InputReport = {
  id: string
  source_key: string
  title: string
  provider?: string | null
  page_count?: number | null
  published_at?: string | null
  quality_pass?: boolean | null
  quality_scope?: string | null
  theme_tag?: string | null
  will_select: boolean
  will_fill_extra?: boolean
  select_role?: string | null
  select_why?: string | null
  exclude_reason?: string | null
}

export type ChatMessage = {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export const THEME_LABEL: Record<ConsensusTheme, string> = {
  datacenter: '데이터센터',
  ai: 'AI',
  physical_ai: '피지컬 AI',
  appliance: '가전',
  display: '디스플레이',
  automotive: '자동차',
  petrochemical: '석유화학',
}

export const STATE_CLASS: Record<ConsensusState, string> = {
  idle: 'idle',
  starting: 'busy',
  active: 'active',
  stopping: 'busy',
  awaiting: 'busy',
  ended: 'idle',
  error: 'danger',
}
