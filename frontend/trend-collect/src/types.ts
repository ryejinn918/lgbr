import type { MediaSourceId } from './lib/mediaSources'
import type { SearchProfileMode } from './lib/themes'

export type SessionState =
  | 'logging_in'
  | 'logged_in'
  | 'logging_out'
  | 'ended'
  | 'error'

export type CrawlState = 'starting' | 'active' | 'stopping' | 'ended' | 'error'

export type SessionRecord = {
  id: string
  source?: string
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

export type CrawlMode =
  | 'auto'
  | 'adhoc'
  | 'all_profiles'
  | MediaSourceId
  | SearchProfileMode

export type CrawlProfileMode = SearchProfileMode

export type CrawlProfile = {
  mode: CrawlProfileMode
  keywords: string[]
  sectors: string[]
  period_months: number
  page_min_label: string
  updated_at: string | null
}

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
  period_months?: number | null
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
  total?: number
  limit?: number
  offset?: number
}

export type TimelineKind = 'session' | 'crawl' | string

export type TimelineItem = {
  id: string
  at: string | null
  kind: TimelineKind
  kind_label: string
  event: string
  stage?: string | null
  level?: string | null
  label: string
  detail: Record<string, unknown>
  ref_id?: string | null
}

export type TimelineSession = {
  id: string
  fnguide_user_id: string | null
  started_at: string | null
  ended_at: string | null
  state: string
  label: string
  end_reason_label: string | null
  event_count: number
  crawl_count: number
}

export type TimelineResponse = {
  ok?: boolean
  items: TimelineSession[]
  total: number
  limit: number
  offset: number
}

export type TimelineSessionEventsResponse = {
  ok?: boolean
  session_id?: string
  items: TimelineItem[]
  total: number
  limit: number
  offset: number
  message?: string
}

export type ReportStatus =
  | 'listed'
  | 'blind'
  | 'downloaded'
  | 'no_download'
  | 'failed'

export type ReportQuality = 'pass' | 'fail' | 'pending' | 'unauditable'

/** Whether summary/audit input was truncated (0/1 or boolean). */
export type QualityExtractMeta = {
  truncated?: 0 | 1 | boolean
}

export type QualityJson = {
  pass?: boolean
  confidence?: number
  has_coherent_framework?: boolean
  has_broad_sector_coverage?: boolean
  scope?: string
  topic?: string
  /** Citation nickname from quality audit; pairs with provider. */
  short_title?: string
  /** Non-FnGuide primary summary (also mirrored to framework_summary). */
  summary?: string | null
  framework_summary?: string | null
  fail_reasons?: string[]
  pass_signals?: string[]
  rationale?: string
  themes?: string[]
  error?: string
  /** Local extract truncation (set on re-audit/summary). */
  extract?: QualityExtractMeta
  [key: string]: unknown
}

export type ReportRecord = {
  id: string
  source?: string | null
  source_key: string
  title: string
  status: ReportStatus | string
  has_file: boolean
  file_name: string | null
  last_seen_at: string | null
  downloaded_at: string | null
  published_at?: string | null
  provider?: string | null
  theme?: string | null
  themes?: string[]
  crawl_profile?: string | null
  /** Public detail-page URL when stored (e.g. PwC); not set for FnGuide. */
  url?: string | null
  page_count?: number | null
  crawl_id?: string | null
  quality?: ReportQuality
  quality_pass?: boolean | null
  quality_scope?: string | null
  quality_confidence?: number | null
  quality_at?: string | null
  quality_model?: string | null
  quality_json?: QualityJson
}

export type AuditState = 'idle' | 'starting' | 'active' | 'ended' | 'error' | string

export type AuditJob = {
  state: AuditState
  label?: string
  pid?: number | null
  started_at?: string | null
  ended_at?: string | null
  message?: string | null
  force?: boolean
  limit?: number | null
  theme?: string | null
  source?: string | null
  report_id?: string | null
  concurrency?: number
  model?: string | null
  stats?: Record<string, number> | null
  can_start?: boolean
}

export type AuditResponse = {
  ok?: boolean
  state: AuditState
  label?: string
  message?: string | null
  audit?: AuditJob | null
  can_start?: boolean
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

export type QualityCounts = {
  pass: number
  fail: number
  pending: number
  unauditable: number
  [key: string]: number
}

export type ThemeCounts = {
  all: number
  ai: number
  datacenter: number
  macroeconomy: number
  physical_ai: number
  appliance: number
  display: number
  automotive: number
  petrochemical: number
  other: number
  [key: string]: number
}

export type ReportsResponse = {
  ok?: boolean
  items: ReportRecord[]
  total: number
  counts: ReportCounts
  quality_counts?: QualityCounts
  theme_counts?: ThemeCounts
  limit: number
  offset: number
  message?: string
}

export type CoverageSourceRow = {
  id: string
  label: string
  counts: number[]
}

export type CoverageResponse = {
  ok?: boolean
  weeks: string[]
  sources: CoverageSourceRow[]
  message?: string
}

export type CollectionCapability =
  | 'feed'
  | 'search'
  | 'fetch_body'
  | 'download'

export type CollectionJobState =
  | 'starting'
  | 'active'
  | 'stopping'
  | 'ended'
  | 'error'

export type CollectionJobRecord = {
  id: string
  source: string
  capability: CollectionCapability | string
  started_at: string | null
  ended_at: string | null
  stop_requested_at: string | null
  pid: number | null
  state: CollectionJobState
  progress?: Record<string, unknown> | null
  message: string | null
  label: string
}

export type CollectionJobResponse = {
  state: CollectionJobState
  label: string
  job: CollectionJobRecord | null
  progress?: Record<string, unknown>
  can_start?: boolean
  ok?: boolean
  message?: string
}

export type NewsArticleRecord = {
  id: string
  source: string
  source_key: string
  title: string
  /** Korean display title for foreign sources (e.g. Nikkei). */
  title_ko?: string | null
  snippet?: string | null
  url: string
  published_at: string | null
  publisher: string | null
  section?: string | null
  first_seen_at: string | null
  last_seen_at: string | null
  attrs?: Record<string, unknown>
  body_text?: string | null
  body_fetched_at?: string | null
  body_fetch_error?: string | null
  has_body?: boolean
}

export type NewsArticleBodyFilter = 'all' | 'yes' | 'no'

export type NewsArticleBodyCounts = {
  all: number
  yes: number
  no: number
  [key: string]: number
}

export type NewsArticleSourceCounts = {
  all: number
  [source: string]: number
}

export type NewsArticlesResponse = {
  ok?: boolean
  source?: string
  has_body?: NewsArticleBodyFilter | string
  items: NewsArticleRecord[]
  total: number
  limit: number
  offset: number
  body_counts?: NewsArticleBodyCounts
  source_counts?: NewsArticleSourceCounts
  message?: string
}
