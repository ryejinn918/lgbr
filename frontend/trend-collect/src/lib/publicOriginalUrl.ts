/** Public original URLs for docs listing (no login wall). */

const REPORT_BLOCKED_SOURCES = new Set(['fnguide'])

function httpUrl(raw: string | null | undefined): string | null {
  const s = (raw || '').trim()
  if (!s.startsWith('http://') && !s.startsWith('https://')) return null
  return s
}

/** Report detail page URL when the source is publicly viewable. */
export function reportPublicOriginalUrl(
  source: string | null | undefined,
  url: string | null | undefined,
): string | null {
  const src = (source || '').trim().toLowerCase()
  if (!src || REPORT_BLOCKED_SOURCES.has(src)) return null
  return httpUrl(url)
}

/** Article URL when present (ARG etc. are public). */
export function articlePublicOriginalUrl(
  url: string | null | undefined,
): string | null {
  return httpUrl(url)
}
