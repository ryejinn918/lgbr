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

export type CrawlProgress = {
  stage?: string
  mode?: string
  asset_id?: string
  limit?: number
  downloaded?: number
  skipped_blind?: number
  skipped_no_download?: number
  list_page?: number
  current_rpt_id?: string
  candidates?: number
  blind?: number
  error?: string
  reason?: string
  [key: string]: unknown
}

export type CrawlEvent = {
  id: string
  crawl_id: string
  at: string
  level: 'debug' | 'info' | 'warn' | 'error' | string
  stage: string
  event: string
  detail: Record<string, unknown>
}

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
  asset_id?: string | null
  debug?: boolean | null
  progress?: CrawlProgress | null
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
  progress?: CrawlProgress
  events?: CrawlEvent[]
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

export type ReportStatus =
  | 'listed'
  | 'blind'
  | 'downloaded'
  | 'no_download'
  | 'failed'

export type ReportRecord = {
  id: string
  source_key: string
  title: string
  status: ReportStatus | string
  has_file: boolean
  file_name: string | null
  last_seen_at: string | null
  downloaded_at: string | null
  published_at?: string | null
  page_count?: number | null
  crawl_id?: string | null
}

export type ReportCounts = {
  all: number
  listed: number
  blind: number
  downloaded: number
  no_download: number
  failed: number
  [key: string]: number
}

export type ReportsResponse = {
  ok?: boolean
  items: ReportRecord[]
  total: number
  counts: ReportCounts
  limit: number
  offset: number
  message?: string
}
