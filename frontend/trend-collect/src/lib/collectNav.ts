import { THEME_LABEL } from './themes'

export type CollectSource = 'fnguide' | 'arg' | 'pwc'
export type CollectStage = 'list' | 'body'
export type ListMeans = 'feed' | 'search'
export type BodyMeans = 'download' | 'fetch'
export type CollectMeans = ListMeans | BodyMeans

export const SOURCES: { id: CollectSource; label: string }[] = [
  { id: 'fnguide', label: 'FnGuide' },
  { id: 'arg', label: 'ARG' },
  { id: 'pwc', label: 'PwC' },
]

export const SOURCE_LABEL: Record<CollectSource, string> = {
  fnguide: 'FnGuide',
  arg: 'ARG',
  pwc: 'PwC',
}

/**
 * Means each source exposes in the collect UI.
 * Only ARG separates list discovery from body fill — FnGuide/PwC run both in one job,
 * so they expose list means only (no 리스트/본문 stage tabs).
 */
export const SOURCE_MEANS: Record<
  CollectSource,
  { list: ListMeans[]; body: BodyMeans[] }
> = {
  fnguide: { list: ['search'], body: [] },
  arg: { list: ['feed'], body: ['fetch'] },
  pwc: { list: ['search'], body: [] },
}

/** True when list and body can be started as separate jobs. */
export function hasSeparateBodyStage(source: CollectSource): boolean {
  return SOURCE_MEANS[source].body.length > 0
}

export function defaultCollectPath(source: CollectSource): string {
  const means = SOURCE_MEANS[source]
  if (means.list.includes('search')) {
    return `/collect/${source}/list/search`
  }
  if (means.list.includes('feed')) {
    return `/collect/${source}/list/feed`
  }
  if (means.body.includes('download')) {
    return `/collect/${source}/body/download`
  }
  if (means.body[0]) {
    return `/collect/${source}/body/${means.body[0]}`
  }
  return `/collect/${source}/list/feed`
}

export function isMeansSupported(
  source: CollectSource,
  stage: CollectStage,
  means: CollectMeans,
): boolean {
  if (stage === 'list') {
    return SOURCE_MEANS[source].list.includes(means as ListMeans)
  }
  return SOURCE_MEANS[source].body.includes(means as BodyMeans)
}

export function isStageSupported(
  source: CollectSource,
  stage: CollectStage,
): boolean {
  if (stage === 'list') return SOURCE_MEANS[source].list.length > 0
  return SOURCE_MEANS[source].body.length > 0
}

export function supportedStages(source: CollectSource): CollectStage[] {
  const out: CollectStage[] = []
  if (isStageSupported(source, 'list')) out.push('list')
  if (isStageSupported(source, 'body')) out.push('body')
  return out
}

export function supportedMeans(
  source: CollectSource,
  stage: CollectStage,
): CollectMeans[] {
  if (stage === 'list') return [...SOURCE_MEANS[source].list]
  return [...SOURCE_MEANS[source].body]
}

export function defaultMeansPath(
  source: CollectSource,
  stage: CollectStage,
): string {
  const means = supportedMeans(source, stage)
  if (means[0]) return `/collect/${source}/${stage}/${means[0]}`
  return defaultCollectPath(source)
}

export function stageLabel(stage: CollectStage): string {
  return stage === 'list' ? '리스트 발굴' : '본문 채우기'
}

export function meansLabel(means: CollectMeans): string {
  switch (means) {
    case 'feed':
      return '피드'
    case 'search':
      return '검색'
    case 'download':
      return '다운로드'
    case 'fetch':
      return '본문읽기'
  }
}

/** Types tab / page title for list-discovery profiles. */
export function discoveryTypeLabel(
  means?: CollectMeans | null,
  source?: CollectSource | null,
): string {
  if (source === 'pwc' && means === 'search') return '목록 · 한국 / 국제'
  if (means === 'feed') return '리스트 발굴 타입 · 피드'
  if (means === 'search') return '검색 프로필'
  return '리스트 발굴 타입'
}

export function crawlModeTypeLabel(mode: string | null | undefined): string {
  if (!mode) return '—'
  if (mode === 'adhoc') return '애드혹'
  if (mode === 'pwc') return 'PwC 애드혹'
  if (mode === 'auto') return '자동'
  return THEME_LABEL[mode] ?? mode
}
