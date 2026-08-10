/** Nikkei feed sections — keep in sync with crawler.sources.nikkei_sections */

export const NIKKEI_SECTIONS = [
  {
    id: 'news',
    label: '速報',
    categoryUrl: 'https://www.nikkei.com/news/category/',
    rssUrl: 'https://assets.wor.jp/rss/rdf/nikkei/news.rdf',
  },
  {
    id: 'business',
    label: 'ビジネス',
    categoryUrl: 'https://www.nikkei.com/news/category/business/',
    rssUrl: 'https://assets.wor.jp/rss/rdf/nikkei/business.rdf',
  },
  {
    id: 'economy',
    label: '政治・経済',
    categoryUrl: 'https://www.nikkei.com/news/category/economy/',
    rssUrl: 'https://assets.wor.jp/rss/rdf/nikkei/economy.rdf',
  },
  {
    id: 'markets',
    label: 'マーケット',
    categoryUrl: 'https://www.nikkei.com/news/category/markets/',
    rssUrl: 'https://assets.wor.jp/rss/rdf/nikkei/markets.rdf',
  },
  {
    id: 'technology',
    label: 'テクノロジー',
    categoryUrl: 'https://www.nikkei.com/news/category/technology/',
    rssUrl: 'https://assets.wor.jp/rss/rdf/nikkei/technology.rdf',
  },
  {
    id: 'international',
    label: '国際・アジア',
    categoryUrl: 'https://www.nikkei.com/news/category/international/',
    rssUrl: 'https://assets.wor.jp/rss/rdf/nikkei/international.rdf',
  },
  {
    id: 'sports',
    label: 'スポーツ',
    categoryUrl: 'https://www.nikkei.com/news/category/sports/',
    rssUrl: 'https://assets.wor.jp/rss/rdf/nikkei/sports.rdf',
  },
  {
    id: 'society',
    label: '社会',
    categoryUrl: 'https://www.nikkei.com/news/category/society/',
    rssUrl: 'https://assets.wor.jp/rss/rdf/nikkei/society.rdf',
  },
] as const

export type NikkeiSectionId = (typeof NIKKEI_SECTIONS)[number]['id']

export const DEFAULT_NIKKEI_SECTION: NikkeiSectionId = 'economy'

const BY_ID = new Map(NIKKEI_SECTIONS.map((s) => [s.id, s]))

export function getNikkeiSection(id: string | null | undefined) {
  if (!id) return null
  return BY_ID.get(id as NikkeiSectionId) ?? null
}
