import type {
  ConsensusRun,
  ConsensusState,
  ConsensusStatusResponse,
  ConsensusTheme,
} from '../types'
import { STATE_CLASS } from '../types'

/** Blocks can_start: worker live or waiting for operator. */
export function isOpenState(state: string | null | undefined): boolean {
  return (
    state === 'starting' ||
    state === 'active' ||
    state === 'stopping' ||
    state === 'awaiting'
  )
}

/** Worker actually running (awaiting is not live). */
export function isLiveState(state: string | null | undefined): boolean {
  return state === 'starting' || state === 'active' || state === 'stopping'
}

export function stateClass(state: ConsensusState | string | null | undefined): string {
  if (!state) return 'idle'
  return STATE_CLASS[state as ConsensusState] || 'idle'
}

export function openRunGlobal(
  status: Pick<ConsensusStatusResponse, 'run'>,
): ConsensusRun | null {
  const run = status.run
  if (!run || !isOpenState(run.state)) return null
  return run
}

export function openRunForTheme(
  status: Pick<ConsensusStatusResponse, 'run'>,
  theme: ConsensusTheme,
): ConsensusRun | null {
  const run = openRunGlobal(status)
  if (!run || run.theme !== theme) return null
  return run
}

export function otherOpenTheme(
  status: Pick<ConsensusStatusResponse, 'run'>,
  theme: ConsensusTheme,
): ConsensusTheme | null {
  const run = openRunGlobal(status)
  if (!run || run.theme === theme) return null
  return run.theme
}
