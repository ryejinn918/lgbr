/** FnGuide search-profile / report theme ids (excludes auto/adhoc). */
export const SEARCH_PROFILE_MODES = [
  'ai',
  'physical_ai',
  'appliance',
  'display',
  'automotive',
  'petrochemical',
] as const

export type SearchProfileMode = (typeof SEARCH_PROFILE_MODES)[number]

export const THEME_LABEL: Record<string, string> = {
  all: '테마전체',
  ai: 'AI/AIDC',
  physical_ai: '피지컬 AI',
  appliance: '가전',
  display: '디스플레이',
  automotive: '자동차',
  petrochemical: '석유화학',
}

/** Longer labels for profile editor headings. */
export const PROFILE_MODE_LABEL: Record<SearchProfileMode, string> = {
  ai: 'AI/AIDC',
  physical_ai: '피지컬 AI',
  appliance: '가전',
  display: '디스플레이',
  automotive: '자동차',
  petrochemical: '석유화학',
}

export function isSearchProfileMode(
  mode: string | null | undefined,
): mode is SearchProfileMode {
  return (
    !!mode && (SEARCH_PROFILE_MODES as readonly string[]).includes(mode)
  )
}
