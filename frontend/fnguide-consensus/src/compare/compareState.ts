import type { StreamToolEvent } from '../lib/chatStream'
import type { ChatMessage, ConsensusRun } from '../types'

export type Mode = 'plain' | 'grounded'
export type FrameTab = 'filled' | 'consensus'

export type UiMessage = ChatMessage & {
  turnId?: string
  tools?: StreamToolEvent[]
  streaming?: boolean
}

export type ColumnState = {
  messages: UiMessage[]
  input: string
  loading: boolean
  phase: string | null
  error: string | null
}

export type LatestState = {
  run: ConsensusRun | null
  filled: string | null
  consensus: string | null
  error: string | null
  loading: boolean
}

export type CompareState = {
  plain: ColumnState
  grounded: ColumnState
  sharedDraft: string
  frameTab: FrameTab
  latest: LatestState
}

export type CompareAction =
  | { type: 'theme_reset' }
  | { type: 'clear_chats' }
  | { type: 'set_input'; mode: Mode; value: string }
  | { type: 'set_shared_draft'; value: string }
  | { type: 'set_frame_tab'; tab: FrameTab }
  | { type: 'latest_loading' }
  | {
      type: 'latest_ok'
      run: ConsensusRun | null
      filled: string | null
      consensus: string | null
    }
  | { type: 'latest_err'; message: string }
  | { type: 'send_start'; mode: Mode; text: string; turnId: string }
  | { type: 'stream_status'; mode: Mode; turnId: string; phase: string }
  | {
      type: 'stream_tool'
      mode: Mode
      turnId: string
      tool: StreamToolEvent
    }
  | { type: 'stream_delta'; mode: Mode; turnId: string; text: string }
  | { type: 'stream_done'; mode: Mode; turnId: string }
  | { type: 'stream_error'; mode: Mode; turnId: string; message: string }

export function emptyColumn(): ColumnState {
  return {
    messages: [],
    input: '',
    loading: false,
    phase: null,
    error: null,
  }
}

export function initialCompareState(): CompareState {
  return {
    plain: emptyColumn(),
    grounded: emptyColumn(),
    sharedDraft: '',
    frameTab: 'filled',
    latest: {
      run: null,
      filled: null,
      consensus: null,
      error: null,
      loading: false,
    },
  }
}

function col(state: CompareState, mode: Mode): ColumnState {
  return mode === 'plain' ? state.plain : state.grounded
}

function setCol(
  state: CompareState,
  mode: Mode,
  next: ColumnState,
): CompareState {
  return mode === 'plain'
    ? { ...state, plain: next }
    : { ...state, grounded: next }
}

function mapTurn(
  messages: UiMessage[],
  turnId: string,
  fn: (m: UiMessage) => UiMessage,
): UiMessage[] {
  return messages.map((m) => (m.turnId === turnId ? fn(m) : m))
}

function historyForSend(messages: UiMessage[]): UiMessage[] {
  return messages.filter((m) => m.content.trim() && !m.streaming)
}

/** Pure: compute api payload + turnId from current state (no mutation). */
export function prepareSend(
  state: CompareState,
  mode: Mode,
  rawText: string,
): { apiMessages: ChatMessage[]; turnId: string; text: string } | null {
  const text = rawText.trim()
  if (!text) return null
  const column = col(state, mode)
  if (column.loading) return null
  if (mode === 'grounded' && !state.latest.run) return null

  const turnId =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `t-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`

  const base = historyForSend(column.messages)
  const apiMessages: ChatMessage[] = [
    ...base.map(({ role, content }) => ({ role, content })),
    { role: 'user', content: text },
  ]
  return { apiMessages, turnId, text }
}

export function compareReducer(
  state: CompareState,
  action: CompareAction,
): CompareState {
  switch (action.type) {
    case 'theme_reset':
      return {
        ...state,
        plain: emptyColumn(),
        grounded: emptyColumn(),
        sharedDraft: '',
        frameTab: 'filled',
        latest: {
          run: null,
          filled: null,
          consensus: null,
          error: null,
          loading: true,
        },
      }

    case 'clear_chats':
      return {
        ...state,
        plain: emptyColumn(),
        grounded: emptyColumn(),
        sharedDraft: '',
      }

    case 'set_input':
      return setCol(state, action.mode, {
        ...col(state, action.mode),
        input: action.value,
      })

    case 'set_shared_draft':
      return { ...state, sharedDraft: action.value }

    case 'set_frame_tab':
      return { ...state, frameTab: action.tab }

    case 'latest_loading':
      return {
        ...state,
        latest: { ...state.latest, loading: true, error: null },
      }

    case 'latest_ok':
      return {
        ...state,
        latest: {
          run: action.run,
          filled: action.filled,
          consensus: action.consensus,
          error: null,
          loading: false,
        },
      }

    case 'latest_err':
      return {
        ...state,
        latest: {
          run: null,
          filled: null,
          consensus: null,
          error: action.message,
          loading: false,
        },
      }

    case 'send_start': {
      const c = col(state, action.mode)
      const base = historyForSend(c.messages)
      const next: ColumnState = {
        messages: [
          ...base,
          { role: 'user', content: action.text },
          {
            role: 'assistant',
            content: '',
            tools: [],
            streaming: true,
            turnId: action.turnId,
          },
        ],
        input: '',
        loading: true,
        phase: 'planning',
        error: null,
      }
      let s = setCol(state, action.mode, next)
      // Clear shared draft when either column starts from "both same" path
      // (caller may also clear; harmless if already empty).
      return s
    }

    case 'stream_status': {
      const c = col(state, action.mode)
      return setCol(state, action.mode, { ...c, phase: action.phase })
    }

    case 'stream_tool': {
      const c = col(state, action.mode)
      return setCol(state, action.mode, {
        ...c,
        phase: 'search',
        messages: mapTurn(c.messages, action.turnId, (m) => ({
          ...m,
          tools: [...(m.tools || []), action.tool],
        })),
      })
    }

    case 'stream_delta': {
      const c = col(state, action.mode)
      return setCol(state, action.mode, {
        ...c,
        phase: 'answer',
        messages: mapTurn(c.messages, action.turnId, (m) => ({
          ...m,
          content: (m.content || '') + action.text,
        })),
      })
    }

    case 'stream_done': {
      const c = col(state, action.mode)
      return setCol(state, action.mode, {
        ...c,
        loading: false,
        phase: null,
        messages: mapTurn(c.messages, action.turnId, (m) => ({
          ...m,
          streaming: false,
        })),
      })
    }

    case 'stream_error': {
      const c = col(state, action.mode)
      const target = c.messages.find((m) => m.turnId === action.turnId)
      const dropEmpty = target && !target.content.trim()
      return setCol(state, action.mode, {
        ...c,
        loading: false,
        phase: null,
        error: action.message,
        messages: dropEmpty
          ? c.messages.filter((m) => m.turnId !== action.turnId)
          : mapTurn(c.messages, action.turnId, (m) => ({
              ...m,
              streaming: false,
            })),
      })
    }

    default:
      return state
  }
}
