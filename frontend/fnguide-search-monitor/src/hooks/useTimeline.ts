import { useCallback, useEffect, useReducer, useRef } from 'react'
import type {
  TimelineItem,
  TimelineResponse,
  TimelineSession,
  TimelineSessionEventsResponse,
} from '../types'

const POLL_MS = 2_500
const DEFAULT_SESSION_LIMIT = 10
const DEFAULT_EVENT_LIMIT = 30

export type TimelineView = {
  sessions: TimelineSession[]
  total: number
  limit: number
  offset: number
  setOffset: (offset: number) => void
  expandedId: string | null
  setExpandedId: (id: string | null) => void
  events: TimelineItem[]
  eventsTotal: number
  eventsLimit: number
  eventsOffset: number
  setEventsOffset: (offset: number) => void
  loading: boolean
  eventsLoading: boolean
  error: string | null
  eventsError: string | null
}

type State = {
  sessions: TimelineSession[]
  total: number
  offset: number
  expandedId: string | null
  /** 사용자가 접었으면 true — 폴링이 자동 펼침 금지 */
  userCollapsed: boolean
  events: TimelineItem[]
  eventsTotal: number
  eventsOffset: number
  loading: boolean
  eventsLoading: boolean
  error: string | null
  eventsError: string | null
}

type Action =
  | { type: 'SESSIONS_LOADING' }
  | {
      type: 'SESSIONS_OK'
      sessions: TimelineSession[]
      total: number
    }
  | { type: 'SESSIONS_ERR'; message: string }
  | { type: 'EXPAND'; id: string }
  | { type: 'SET_SESSION_OFFSET'; offset: number }
  | { type: 'SET_EVENTS_OFFSET'; offset: number }
  | { type: 'EVENTS_LOADING' }
  | {
      type: 'EVENTS_OK'
      items: TimelineItem[]
      total: number
    }
  | { type: 'EVENTS_ERR'; message: string }
  | { type: 'EVENTS_CLEAR' }

const initialState: State = {
  sessions: [],
  total: 0,
  offset: 0,
  expandedId: null,
  userCollapsed: true,
  events: [],
  eventsTotal: 0,
  eventsOffset: 0,
  loading: true,
  eventsLoading: false,
  error: null,
  eventsError: null,
}

function clearEvents(): Pick<
  State,
  'events' | 'eventsTotal' | 'eventsOffset' | 'eventsLoading' | 'eventsError'
> {
  return {
    events: [],
    eventsTotal: 0,
    eventsOffset: 0,
    eventsLoading: false,
    eventsError: null,
  }
}

/** 자동 펼침 없음. 사용자가 연 카드가 목록에 있을 때만 유지. */
function resolveExpanded(
  state: State,
  sessions: TimelineSession[],
): { expandedId: string | null; clearedEvents: boolean } {
  if (
    !state.userCollapsed &&
    state.expandedId &&
    sessions.some((s) => s.id === state.expandedId)
  ) {
    return { expandedId: state.expandedId, clearedEvents: false }
  }
  return {
    expandedId: null,
    clearedEvents: state.expandedId != null,
  }
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'SESSIONS_LOADING':
      return { ...state, loading: true }
    case 'SESSIONS_OK': {
      const { expandedId, clearedEvents } = resolveExpanded(
        state,
        action.sessions,
      )
      return {
        ...state,
        sessions: action.sessions,
        total: action.total,
        loading: false,
        error: null,
        expandedId,
        ...(clearedEvents ? clearEvents() : {}),
      }
    }
    case 'SESSIONS_ERR':
      return {
        ...state,
        loading: false,
        error: action.message,
      }
    case 'EXPAND': {
      const collapsing = state.expandedId === action.id
      if (collapsing) {
        return {
          ...state,
          expandedId: null,
          userCollapsed: true,
          ...clearEvents(),
        }
      }
      return {
        ...state,
        expandedId: action.id,
        userCollapsed: false,
        ...clearEvents(),
      }
    }
    case 'SET_SESSION_OFFSET':
      return {
        ...state,
        offset: action.offset,
        userCollapsed: true,
        expandedId: null,
        loading: true,
        ...clearEvents(),
      }
    case 'SET_EVENTS_OFFSET':
      return {
        ...state,
        eventsOffset: action.offset,
        events: [],
        eventsLoading: true,
        eventsError: null,
      }
    case 'EVENTS_LOADING':
      return { ...state, eventsLoading: true }
    case 'EVENTS_OK':
      return {
        ...state,
        events: action.items,
        eventsTotal: action.total,
        eventsLoading: false,
        eventsError: null,
      }
    case 'EVENTS_ERR':
      return {
        ...state,
        eventsLoading: false,
        eventsError: action.message,
      }
    case 'EVENTS_CLEAR':
      return { ...state, ...clearEvents() }
    default:
      return state
  }
}

export function useTimeline(opts?: {
  limit?: number
  eventLimit?: number
}): TimelineView {
  const limit = opts?.limit ?? DEFAULT_SESSION_LIMIT
  const eventsLimit = opts?.eventLimit ?? DEFAULT_EVENT_LIMIT
  const [state, dispatch] = useReducer(reducer, initialState)
  const sessionsGen = useRef(0)
  const eventsGen = useRef(0)

  const fetchSessions = useCallback(
    async (offset: number) => {
      const gen = ++sessionsGen.current
      const params = new URLSearchParams({
        limit: String(limit),
        offset: String(offset),
      })
      try {
        const res = await fetch(`/api/timeline?${params}`)
        const data = (await res.json()) as TimelineResponse & {
          message?: string
        }
        if (gen !== sessionsGen.current) return
        if (!res.ok) {
          throw new Error(data.message || `HTTP ${res.status}`)
        }
        dispatch({
          type: 'SESSIONS_OK',
          sessions: data.items ?? [],
          total: data.total ?? 0,
        })
      } catch (err) {
        if (gen !== sessionsGen.current) return
        dispatch({
          type: 'SESSIONS_ERR',
          message: err instanceof Error ? err.message : 'fetch failed',
        })
      }
    },
    [limit],
  )

  const fetchEvents = useCallback(
    async (sessionId: string | null, eventsOffset: number) => {
      const gen = ++eventsGen.current
      if (!sessionId) {
        dispatch({ type: 'EVENTS_CLEAR' })
        return
      }
      dispatch({ type: 'EVENTS_LOADING' })
      const params = new URLSearchParams({
        limit: String(eventsLimit),
        offset: String(eventsOffset),
      })
      try {
        const res = await fetch(
          `/api/timeline/sessions/${sessionId}?${params}`,
        )
        const data = (await res.json()) as TimelineSessionEventsResponse
        if (gen !== eventsGen.current) return
        if (!res.ok) {
          throw new Error(data.message || `HTTP ${res.status}`)
        }
        dispatch({
          type: 'EVENTS_OK',
          items: data.items ?? [],
          total: data.total ?? 0,
        })
      } catch (err) {
        if (gen !== eventsGen.current) return
        dispatch({
          type: 'EVENTS_ERR',
          message: err instanceof Error ? err.message : 'fetch failed',
        })
      }
    },
    [eventsLimit],
  )

  useEffect(() => {
    dispatch({ type: 'SESSIONS_LOADING' })
    void fetchSessions(state.offset)
    const id = window.setInterval(() => {
      void fetchSessions(state.offset)
    }, POLL_MS)
    return () => {
      sessionsGen.current += 1
      window.clearInterval(id)
    }
  }, [fetchSessions, state.offset])

  useEffect(() => {
    void fetchEvents(state.expandedId, state.eventsOffset)
    if (!state.expandedId) return undefined
    const id = window.setInterval(() => {
      void fetchEvents(state.expandedId, state.eventsOffset)
    }, POLL_MS)
    return () => {
      eventsGen.current += 1
      window.clearInterval(id)
    }
  }, [fetchEvents, state.expandedId, state.eventsOffset])

  return {
    sessions: state.sessions,
    total: state.total,
    limit,
    offset: state.offset,
    setOffset: (next) => {
      dispatch({ type: 'SET_SESSION_OFFSET', offset: Math.max(0, next) })
    },
    expandedId: state.expandedId,
    setExpandedId: (id) => {
      if (id == null) return
      dispatch({ type: 'EXPAND', id })
    },
    events: state.events,
    eventsTotal: state.eventsTotal,
    eventsLimit,
    eventsOffset: state.eventsOffset,
    setEventsOffset: (next) => {
      dispatch({ type: 'SET_EVENTS_OFFSET', offset: Math.max(0, next) })
    },
    loading: state.loading,
    eventsLoading: state.eventsLoading,
    error: state.error,
    eventsError: state.eventsError,
  }
}
