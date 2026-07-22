export type SessionState =
  | 'idle'
  | 'logging_in'
  | 'active'
  | 'logging_out'
  | 'error'

export type SessionStatus = {
  state: SessionState
  user_id: string | null
  started_at: string | null
  updated_at: string | null
  pid: number | null
  current_url: string | null
  step: string | null
  message: string | null
}
