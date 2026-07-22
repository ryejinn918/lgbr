export type SessionState =
  | 'logging_in'
  | 'logged_in'
  | 'logging_out'
  | 'ended'
  | 'error'

export type CrawlState = 'starting' | 'active' | 'stopping' | 'ended' | 'error'

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

export type CrawlMode = 'auto' | 'adhoc' | 'datacenter'

export type CrawlRecord = {
  id: string
  session_id: string | null
  started_at: string | null
  ended_at: string | null
  stop_requested_at: string | null
  pid: number | null
  state: CrawlState
  mode?: CrawlMode | null
  report_limit?: number | null
  cdp_port?: number | null
  cdp_http_url?: string | null
  message: string | null
  label: string
}

export type SessionResponse = {
  state: SessionState
  label: string
  session: SessionRecord | null
}

export type DbConnectInfo = {
  host: string
  port: string
  database: string
  user: string
}

export type CrawlResponse = {
  state: CrawlState
  label: string
  crawl: CrawlRecord | null
  session: SessionResponse
  can_start?: boolean
  /** Exact SQL to clear a blocking error after investigation. */
  unblock_sql?: string | null
  db?: DbConnectInfo | null
  unblock_text?: string | null
}

export type HistoryResponse = {
  items: SessionRecord[]
}
