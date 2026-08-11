import { PROFILE_MODE_LABEL, isSearchProfileMode } from './themes'
import {
  MEDIA_SOURCES,
  getMediaSource,
  isMediaAdhocMode,
  isMediaSourceId,
} from './mediaSources'

/** Crawl modes that belong on the FnGuide dashboard card. */
export function isFnguideCrawlMode(mode: string | null | undefined): boolean {
  if (!mode) return false
  if (isMediaAdhocMode(mode)) return false
  return mode === 'auto' || mode === 'adhoc' || isSearchProfileMode(mode)
}

export type CollectSource = 'fnguide' | 'arg' | (typeof MEDIA_SOURCES)[number]['id']
export type CollectStage = 'list' | 'body'
export type ListMeans = 'feed' | 'search'
export type BodyMeans = 'download' | 'fetch'
export type CollectMeans = ListMeans | BodyMeans

/** L2 job chip + optional L3 settings screen. */
export type CollectJob = {
  id: string
  label: string
  stage: CollectStage
  means: CollectMeans
  /** L3 settings chip label; null = no L3 row. */
  settingsLabel: string | null
}

const REPORT_MEDIA_SOURCES = MEDIA_SOURCES.filter((s) => s.id !== 'nikkei')
const NIKKEI_MEDIA = MEDIA_SOURCES.find((s) => s.id === 'nikkei')

/** Display order: FnGuide → reports → news (ARG, Nikkei). */
export const SOURCES: { id: CollectSource; label: string }[] = [
  { id: 'fnguide', label: 'FnGuide' },
  ...REPORT_MEDIA_SOURCES.map((s) => ({
    id: s.id as CollectSource,
    label: s.label,
  })),
  { id: 'arg', label: 'ARG' },
  ...(NIKKEI_MEDIA
    ? [{ id: 'nikkei' as CollectSource, label: NIKKEI_MEDIA.label }]
    : []),
]

export const SOURCE_LABEL: Record<string, string> = {
  fnguide: 'FnGuide',
  arg: 'ARG',
  ...Object.fromEntries(MEDIA_SOURCES.map((s) => [s.id, s.label])),
}

const CORE_JOBS: Record<'fnguide' | 'arg', CollectJob[]> = {
  fnguide: [
    {
      id: 'search',
      label: '검색',
      stage: 'list',
      means: 'search',
      settingsLabel: '프로필',
    },
  ],
  arg: [
    {
      id: 'feed',
      label: '피드',
      stage: 'list',
      means: 'feed',
      settingsLabel: '타입',
    },
    // Body fetch hidden — compliance: do not expose body retention UI.
    // {
    //   id: 'body',
    //   label: '본문',
    //   stage: 'body',
    //   means: 'fetch',
    //   settingsLabel: null,
    // },
  ],
}

function mediaJobs(sourceId: string): CollectJob[] {
  const meta = getMediaSource(sourceId)
  if (meta?.hasFeed) {
    const jobs: CollectJob[] = [
      {
        id: 'feed',
        label: '피드',
        stage: 'list',
        means: 'feed',
        settingsLabel: '섹션',
      },
    ]
    if (meta.hasFetchBody) {
      jobs.push({
        id: 'body',
        label: '본문',
        stage: 'body',
        means: 'fetch',
        settingsLabel: null,
      })
    }
    return jobs
  }
  return [
    {
      id: 'search',
      label: meta?.hasSearch === false ? '애드혹' : '검색',
      stage: 'list',
      means: 'search',
      settingsLabel: meta?.hasCatalogs ? '목록' : null,
    },
  ]
}

export function jobsFor(source: CollectSource): CollectJob[] {
  if (source === 'fnguide' || source === 'arg') return CORE_JOBS[source]
  return mediaJobs(source)
}

export function findJob(
  source: CollectSource,
  stage: CollectStage,
  means: CollectMeans,
): CollectJob | null {
  return (
    jobsFor(source).find((j) => j.stage === stage && j.means === means) ?? null
  )
}

export function jobPath(source: CollectSource, job: CollectJob): string {
  return `/collect/${source}/${job.stage}/${job.means}`
}

export function settingsPath(source: CollectSource, job: CollectJob): string {
  return `${jobPath(source, job)}/types`
}

export function jobHasSettings(job: CollectJob): boolean {
  return job.settingsLabel != null
}

/**
 * Means each source exposes — derived from jobs for URL validation.
 */
export const SOURCE_MEANS: Record<
  string,
  { list: ListMeans[]; body: BodyMeans[] }
> = Object.fromEntries(
  SOURCES.map((s) => {
    const list: ListMeans[] = []
    const body: BodyMeans[] = []
    for (const j of jobsFor(s.id)) {
      if (j.stage === 'list') list.push(j.means as ListMeans)
      else body.push(j.means as BodyMeans)
    }
    return [s.id, { list, body }]
  }),
)

export function isCollectSource(value: string | undefined): value is CollectSource {
  return value === 'fnguide' || value === 'arg' || isMediaSourceId(value)
}

/** True when list and body can be started as separate jobs. */
export function hasSeparateBodyStage(source: CollectSource): boolean {
  return jobsFor(source).some((j) => j.stage === 'body')
}

export function defaultCollectPath(source: CollectSource): string {
  const first = jobsFor(source)[0]
  if (first) return jobPath(source, first)
  return `/collect/${source}/list/feed`
}

export function isMeansSupported(
  source: CollectSource,
  stage: CollectStage,
  means: CollectMeans,
): boolean {
  return findJob(source, stage, means) != null
}

export function isStageSupported(
  source: CollectSource,
  stage: CollectStage,
): boolean {
  return jobsFor(source).some((j) => j.stage === stage)
}

export function supportedStages(source: CollectSource): CollectStage[] {
  const seen = new Set<CollectStage>()
  const out: CollectStage[] = []
  for (const j of jobsFor(source)) {
    if (!seen.has(j.stage)) {
      seen.add(j.stage)
      out.push(j.stage)
    }
  }
  return out
}

export function supportedMeans(
  source: CollectSource,
  stage: CollectStage,
): CollectMeans[] {
  return jobsFor(source)
    .filter((j) => j.stage === stage)
    .map((j) => j.means)
}

export function defaultMeansPath(
  source: CollectSource,
  stage: CollectStage,
): string {
  const job = jobsFor(source).find((j) => j.stage === stage)
  if (job) return jobPath(source, job)
  return defaultCollectPath(source)
}

export function stageLabel(stage: CollectStage): string {
  return stage === 'list' ? '검색' : '본문'
}

export function meansLabel(means: CollectMeans): string {
  switch (means) {
    case 'feed':
      return '피드'
    case 'search':
      return '검색'
    case 'download':
      return '처리'
    case 'fetch':
      return '처리'
  }
}

/** L3 settings label for the current job (or fallback). */
export function discoveryTypeLabel(
  means?: CollectMeans | null,
  source?: CollectSource | null,
): string {
  if (source && means) {
    const stage: CollectStage =
      means === 'fetch' || means === 'download' ? 'body' : 'list'
    const job = findJob(source, stage, means)
    if (job?.settingsLabel) return job.settingsLabel
  }
  return '설정'
}

export function crawlModeTypeLabel(mode: string | null | undefined): string {
  if (!mode) return '—'
  if (mode === 'adhoc') return '애드혹'
  if (mode === 'auto') return '자동'
  const media = getMediaSource(mode)
  if (media) return `${media.label} 애드혹`
  return PROFILE_MODE_LABEL[mode as keyof typeof PROFILE_MODE_LABEL] ?? mode
}

export function mediaHasSearch(source: CollectSource): boolean {
  return getMediaSource(source)?.hasSearch === true
}

export function mediaHasCatalogs(source: CollectSource): boolean {
  return getMediaSource(source)?.hasCatalogs === true
}
