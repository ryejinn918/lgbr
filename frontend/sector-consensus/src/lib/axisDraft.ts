export type AxisFields = {
  thesis: string
  cutLogic: string
  pillars: string
}

export type AxisDraft = {
  runId: string
  base: AxisFields
  values: AxisFields
  updatedAt: string
}

const PREFIX = 'lgbr:consensus:axis-draft:'

function key(runId: string): string {
  return `${PREFIX}${runId}`
}

export function sameAxisFields(a: AxisFields, b: AxisFields): boolean {
  return (
    a.thesis === b.thesis &&
    a.cutLogic === b.cutLogic &&
    a.pillars === b.pillars
  )
}

function isAxisFields(value: unknown): value is AxisFields {
  if (!value || typeof value !== 'object') return false
  const fields = value as Partial<AxisFields>
  return (
    typeof fields.thesis === 'string' &&
    typeof fields.cutLogic === 'string' &&
    typeof fields.pillars === 'string'
  )
}

export function readAxisDraft(runId: string): AxisDraft | null {
  try {
    const raw = window.localStorage.getItem(key(runId))
    if (!raw) return null
    const value = JSON.parse(raw) as Partial<AxisDraft>
    if (
      value.runId !== runId ||
      !isAxisFields(value.base) ||
      !isAxisFields(value.values) ||
      typeof value.updatedAt !== 'string'
    ) {
      window.localStorage.removeItem(key(runId))
      return null
    }
    return value as AxisDraft
  } catch {
    return null
  }
}

export function writeAxisDraft(
  runId: string,
  base: AxisFields,
  values: AxisFields,
  currentServer: AxisFields = base,
): void {
  try {
    if (sameAxisFields(currentServer, values)) {
      window.localStorage.removeItem(key(runId))
      return
    }
    const draft: AxisDraft = {
      runId,
      base,
      values,
      updatedAt: new Date().toISOString(),
    }
    window.localStorage.setItem(key(runId), JSON.stringify(draft))
  } catch {
    // Storage can be unavailable in private or locked-down browser contexts.
  }
}

export function clearAxisDraft(runId: string): void {
  try {
    window.localStorage.removeItem(key(runId))
  } catch {
    // Nothing else to clean up when storage is unavailable.
  }
}
