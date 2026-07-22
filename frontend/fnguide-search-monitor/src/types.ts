export type SessionState =
  | 'logging_in'
  | 'logged_in'
  | 'logging_out'
  | 'ended'
  | 'error'

export type SessionRecord = {
  id: string
  fnguide_user_id: string
  started_at: string | null
  ended_at: string | null
  last_used_at: string | null
  lease_until: string | null
  logout_requested_at: string | null
  pid: number | null
  current_url: string | null
  step: string | null
  message: string | null
  state: SessionState
  end_reason: string | null
  label: string
  end_reason_label: string | null
}

export type SessionResponse = {
  state: SessionState
  label: string
  session: SessionRecord | null
}

export type HistoryResponse = {
  items: SessionRecord[]
}
