/** BCG search profiles — keep in sync with crawler.sources.bcg_browser.PROFILES */
export const BCG_PROFILES = [
  {
    id: 'report',
    label: 'Featured Insights',
    periodMonths: 3,
    listUrls: ['https://www.bcg.com/publications'],
  },
  {
    id: 'ai',
    label: 'AI',
    periodMonths: 3,
    listUrls: [
      'https://www.bcg.com/capabilities/artificial-intelligence',
      'https://www.bcg.com/capabilities/artificial-intelligence/generative-ai',
    ],
  },
  {
    id: 'datacenter',
    label: '데이터센터',
    periodMonths: 3,
    listUrls: [
      'https://www.bcg.com/capabilities/digital-technology-data/cloud-computing',
      'https://www.bcg.com/industries/energy/power-utilities',
      'https://www.bcg.com/industries/technology-media-telecommunications/semiconductors',
    ],
  },
  {
    id: 'physical_ai',
    label: '피지컬 AI',
    periodMonths: 3,
    listUrls: [
      'https://www.bcg.com/capabilities/manufacturing/industry-4.0',
      'https://www.bcg.com/industries/industrial-goods/machinery-industrial-automation',
    ],
  },
  {
    id: 'appliance',
    label: '가전',
    periodMonths: 3,
    listUrls: [
      'https://www.bcg.com/industries/consumer-products-industry/overview',
    ],
  },
  {
    id: 'display',
    label: '디스플레이',
    periodMonths: 3,
    listUrls: [
      'https://www.bcg.com/industries/technology-media-telecommunications/future-of-television',
      'https://www.bcg.com/industries/technology-media-telecommunications/technology-industry',
    ],
  },
  {
    id: 'automotive',
    label: '자동차',
    periodMonths: 3,
    listUrls: ['https://www.bcg.com/industries/automotive/overview'],
  },
  {
    id: 'petrochemical',
    label: '석유화학',
    periodMonths: 3,
    listUrls: [
      'https://www.bcg.com/industries/industrial-goods/chemicals',
    ],
  },
] as const

export type BcgProfileId = (typeof BCG_PROFILES)[number]['id']

export const DEFAULT_BCG_PROFILE: BcgProfileId = 'report'

const BY_ID = new Map(BCG_PROFILES.map((p) => [p.id, p]))

export function getBcgProfile(id: string | null | undefined) {
  if (!id) return null
  return BY_ID.get(id as BcgProfileId) ?? null
}
