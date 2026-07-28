import type { ConsensusTheme } from '../types'

export const THEMES: ConsensusTheme[] = [
  'ai',
  'physical_ai',
  'appliance',
  'display',
  'automotive',
  'petrochemical',
]

export const DEFAULT_THEME: ConsensusTheme = 'ai'

export type AppTab = 'axes' | 'frames'

export function parseTheme(raw: string | null | undefined): ConsensusTheme {
  // Legacy slug: datacenter merged into ai (AI/AIDC).
  if (raw === 'datacenter') return 'ai'
  if (raw && THEMES.includes(raw as ConsensusTheme)) return raw as ConsensusTheme
  return DEFAULT_THEME
}

export function themePath(theme: ConsensusTheme, tab: AppTab): string {
  return `/${theme}/${tab}`
}

/** Path segment after /:theme/ — axes | frames (legacy select → axes) */
export function parseTab(pathname: string): AppTab {
  const part = pathname.split('/').filter(Boolean)[1]
  if (part === 'frames') return 'frames'
  return 'axes'
}
