import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { ConsensusTheme } from '../types'
import {
  compareReducer,
  initialCompareState,
  type CompareAction,
  type CompareState,
  type ColumnState,
  type FrameTab,
  type UiMessage,
} from './compareState'

const STORAGE_KEY = 'lgbr.compare.v1'
const THEMES: ConsensusTheme[] = ['datacenter', 'ai', 'physical_ai']

type PersistedColumn = {
  messages: UiMessage[]
  input: string
}

type PersistedSlice = {
  plain: PersistedColumn
  grounded: PersistedColumn
  sharedDraft: string
  frameTab: FrameTab
}

type PersistedBag = Partial<Record<ConsensusTheme, PersistedSlice>>

type StateByTheme = Record<ConsensusTheme, CompareState>

type CompareStoreValue = {
  byTheme: StateByTheme
  dispatchFor: (theme: ConsensusTheme, action: CompareAction) => void
}

const CompareStoreContext = createContext<CompareStoreValue | null>(null)

function normalizeMessages(messages: UiMessage[] | undefined): UiMessage[] {
  if (!Array.isArray(messages)) return []
  return messages
    .filter((m) => m && (m.role === 'user' || m.role === 'assistant'))
    .map((m) => ({
      role: m.role,
      content: String(m.content || ''),
      turnId: m.turnId,
      tools: m.tools,
      streaming: false,
    }))
    .filter((m) => m.content.trim() || m.role === 'user')
}

function normalizeColumn(raw: PersistedColumn | undefined): ColumnState {
  return {
    messages: normalizeMessages(raw?.messages),
    input: typeof raw?.input === 'string' ? raw.input : '',
    loading: false,
    phase: null,
    error: null,
  }
}

function emptyStateByTheme(): StateByTheme {
  return {
    datacenter: initialCompareState(),
    ai: initialCompareState(),
    physical_ai: initialCompareState(),
  }
}

function loadFromStorage(): StateByTheme {
  const base = emptyStateByTheme()
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return base
    const parsed = JSON.parse(raw) as PersistedBag
    for (const theme of THEMES) {
      const slice = parsed[theme]
      if (!slice) continue
      base[theme] = {
        ...initialCompareState(),
        plain: normalizeColumn(slice.plain),
        grounded: normalizeColumn(slice.grounded),
        sharedDraft:
          typeof slice.sharedDraft === 'string' ? slice.sharedDraft : '',
        frameTab:
          slice.frameTab === 'consensus' || slice.frameTab === 'filled'
            ? slice.frameTab
            : 'filled',
      }
    }
  } catch {
    /* ignore corrupt storage */
  }
  return base
}

function toPersisted(state: StateByTheme): PersistedBag {
  const out: PersistedBag = {}
  for (const theme of THEMES) {
    const s = state[theme]
    out[theme] = {
      plain: { messages: s.plain.messages, input: s.plain.input },
      grounded: { messages: s.grounded.messages, input: s.grounded.input },
      sharedDraft: s.sharedDraft,
      frameTab: s.frameTab,
    }
  }
  return out
}

export function CompareStoreProvider({ children }: { children: ReactNode }) {
  const [byTheme, setByTheme] = useState<StateByTheme>(() => loadFromStorage())

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(toPersisted(byTheme)))
    } catch {
      /* quota / private mode */
    }
  }, [byTheme])

  const dispatchFor = useCallback(
    (theme: ConsensusTheme, action: CompareAction) => {
      setByTheme((prev) => {
        const current = prev[theme] ?? initialCompareState()
        // Sector switch must keep chats; ignore theme_reset clears.
        if (action.type === 'theme_reset') {
          return prev
        }
        return {
          ...prev,
          [theme]: compareReducer(current, action),
        }
      })
    },
    [],
  )

  const value = useMemo(
    () => ({ byTheme, dispatchFor }),
    [byTheme, dispatchFor],
  )

  return (
    <CompareStoreContext.Provider value={value}>
      {children}
    </CompareStoreContext.Provider>
  )
}

export function useCompareStore(theme: ConsensusTheme): {
  state: CompareState
  dispatch: (action: CompareAction) => void
} {
  const ctx = useContext(CompareStoreContext)
  if (!ctx) {
    throw new Error('useCompareStore requires CompareStoreProvider')
  }
  const dispatch = useCallback(
    (action: CompareAction) => ctx.dispatchFor(theme, action),
    [ctx.dispatchFor, theme],
  )
  return { state: ctx.byTheme[theme] ?? initialCompareState(), dispatch }
}
