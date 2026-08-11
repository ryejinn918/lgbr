/** KPMG search profiles — keep in sync with crawler.sources.kpmg_http.PROFILES */
export const KPMG_PROFILES = [
  {
    id: 'report',
    label: 'Report / Hub',
    periodMonths: 3,
    queries: ['*', 'report'],
  },
  {
    id: 'ai',
    label: 'AI',
    periodMonths: 3,
    queries: [
      'AI',
      'AI semiconductor',
      'generative AI',
      'LLM',
      'talent',
      'workforce',
    ],
  },
  {
    id: 'datacenter',
    label: '데이터센터',
    periodMonths: 3,
    queries: ['data center', 'AIDC', 'power', 'cooling'],
  },
  {
    id: 'physical_ai',
    label: '피지컬 AI',
    periodMonths: 3,
    queries: ['Physical AI', 'humanoid', 'robotics', 'robot', 'on-device'],
  },
  {
    id: 'appliance',
    label: '가전',
    periodMonths: 3,
    queries: ['appliance', 'consumer electronics', 'HVAC', 'TV'],
  },
  {
    id: 'display',
    label: '디스플레이',
    periodMonths: 3,
    queries: ['display', 'OLED', 'panel'],
  },
  {
    id: 'automotive',
    label: '자동차',
    periodMonths: 3,
    queries: ['automotive', 'EV', 'mobility', 'battery', 'SDV'],
  },
  {
    id: 'petrochemical',
    label: '석유화학',
    periodMonths: 3,
    queries: ['chemicals', 'petrochemical', 'chemical'],
  },
] as const

export type KpmgProfileId = (typeof KPMG_PROFILES)[number]['id']

export const DEFAULT_KPMG_PROFILE: KpmgProfileId = 'report'

const BY_ID = new Map(KPMG_PROFILES.map((p) => [p.id, p]))

export function getKpmgProfile(id: string | null | undefined) {
  if (!id) return null
  return BY_ID.get(id as KpmgProfileId) ?? null
}
