import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  clearAxisDraft,
  readAxisDraft,
  sameAxisFields,
  writeAxisDraft,
  type AxisFields,
} from './axisDraft'

class MemoryStorage {
  private values = new Map<string, string>()

  getItem(key: string): string | null {
    return this.values.get(key) ?? null
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value)
  }

  removeItem(key: string): void {
    this.values.delete(key)
  }
}

const base: AxisFields = {
  thesis: '주제',
  cutLogic: '축 나눈 이유',
  pillars: '축 1\n축 2',
}

describe('axis draft persistence', () => {
  beforeEach(() => {
    vi.stubGlobal('window', { localStorage: new MemoryStorage() })
  })

  it('restores an edited draft by run id', () => {
    const values = { ...base, thesis: '수정한 주제' }
    writeAxisDraft('run-1', base, values)

    expect(readAxisDraft('run-1')).toMatchObject({
      runId: 'run-1',
      base,
      values,
    })
    expect(readAxisDraft('run-2')).toBeNull()
  })

  it('removes the draft when edits return to the server value', () => {
    writeAxisDraft('run-1', base, { ...base, thesis: '수정' })
    writeAxisDraft('run-1', base, base)

    expect(readAxisDraft('run-1')).toBeNull()
  })

  it('does not drop a conflicted draft that matches only the old server value', () => {
    const currentServer = { ...base, thesis: '서버에서 바뀐 주제' }
    writeAxisDraft('run-1', base, base, currentServer)

    expect(readAxisDraft('run-1')).toMatchObject({
      base,
      values: base,
    })
  })

  it('keeps server and draft values distinguishable', () => {
    expect(sameAxisFields(base, base)).toBe(true)
    expect(sameAxisFields(base, { ...base, pillars: '새 축 1\n새 축 2' })).toBe(
      false,
    )
  })

  it('clears a submitted draft', () => {
    writeAxisDraft('run-1', base, { ...base, thesis: '제출할 주제' })
    clearAxisDraft('run-1')

    expect(readAxisDraft('run-1')).toBeNull()
  })
})
