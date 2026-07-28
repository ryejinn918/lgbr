import type { ConsensusTheme } from '../types'

export const THEMES: ConsensusTheme[] = [
  'ai',
  'datacenter',
  'physical_ai',
  'appliance',
  'display',
  'automotive',
  'petrochemical',
]

export const DEFAULT_THEME: ConsensusTheme = 'ai'

export type AppTab = 'compare' | 'frames' | 'ops' | 'select'

export function parseTheme(raw: string | null | undefined): ConsensusTheme {
  if (raw && THEMES.includes(raw as ConsensusTheme)) return raw as ConsensusTheme
  return DEFAULT_THEME
}

export function themePath(theme: ConsensusTheme, tab: AppTab): string {
  return `/${theme}/${tab}`
}

/** Path segment after /:theme/ — compare | frames | ops | select */
export function parseTab(pathname: string): AppTab {
  const part = pathname.split('/').filter(Boolean)[1]
  if (part === 'frames' || part === 'ops' || part === 'select') return part
  return 'compare'
}
