/** Public original URLs for docs listing (no login wall). */

function httpUrl(raw: string | null | undefined): string | null {
  const s = (raw || '').trim()
  if (!s.startsWith('http://') && !s.startsWith('https://')) return null
  return s
}

/** Article URL when present (ARG etc. are public). */
export function articlePublicOriginalUrl(
  url: string | null | undefined,
): string | null {
  return httpUrl(url)
}
