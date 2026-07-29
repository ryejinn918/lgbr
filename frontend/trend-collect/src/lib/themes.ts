/** FnGuide / Deloitte crawl-profile mode ids (no macroeconomy crawl). */
export const SEARCH_PROFILE_MODES = [
  'ai',
  'datacenter',
  'physical_ai',
  'appliance',
  'display',
  'automotive',
  'petrochemical',
] as const

export type SearchProfileMode = (typeof SEARCH_PROFILE_MODES)[number]

/** Report content themes (attrs.themes[]); includes macroeconomy. */
export const REPORT_THEMES = [
  'ai',
  'datacenter',
  'macroeconomy',
  'physical_ai',
  'appliance',
  'display',
  'automotive',
  'petrochemical',
] as const

export type ReportTheme = (typeof REPORT_THEMES)[number]

export const THEME_LABEL: Record<string, string> = {
  all: '주제전체',
  ai: 'AI',
  datacenter: '데이터센터',
  macroeconomy: '거시경제',
  physical_ai: '피지컬 AI',
  appliance: '가전',
  display: '디스플레이',
  automotive: '자동차',
  petrochemical: '석유화학',
}

/** Crawl-profile labels for Run / profile editor. */
export const PROFILE_MODE_LABEL: Record<SearchProfileMode, string> = {
  ai: 'AI',
  datacenter: '데이터센터',
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

export function isReportTheme(
  theme: string | null | undefined,
): theme is ReportTheme {
  return !!theme && (REPORT_THEMES as readonly string[]).includes(theme)
}
