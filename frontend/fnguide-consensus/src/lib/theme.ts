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

export type AppTab = 'axes' | 'select' | 'frames' | 'ops'

export function parseTheme(raw: string | null | undefined): ConsensusTheme {
  if (raw && THEMES.includes(raw as ConsensusTheme)) return raw as ConsensusTheme
  return DEFAULT_THEME
}

export function themePath(theme: ConsensusTheme, tab: AppTab): string {
  return `/${theme}/${tab}`
}

/** Path segment after /:theme/ — axes | select | frames | ops */
export function parseTab(pathname: string): AppTab {
  const part = pathname.split('/').filter(Boolean)[1]
  if (
    part === 'axes' ||
    part === 'select' ||
    part === 'frames' ||
    part === 'ops'
  ) {
    return part
  }
  return 'axes'
}
