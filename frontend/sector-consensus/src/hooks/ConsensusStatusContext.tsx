import { createContext, useContext, type ReactNode } from 'react'
import type { ConsensusTheme } from '../types'
import { useConsensusStatus } from './useConsensusStatus'

type ConsensusStatusValue = ReturnType<typeof useConsensusStatus>

const ConsensusStatusContext = createContext<ConsensusStatusValue | null>(null)

export function ConsensusStatusProvider({
  theme,
  children,
}: {
  theme: ConsensusTheme
  children: ReactNode
}) {
  const value = useConsensusStatus(theme)
  return (
    <ConsensusStatusContext.Provider value={value}>
      {children}
    </ConsensusStatusContext.Provider>
  )
}

export function useConsensusStatusContext(): ConsensusStatusValue {
  const ctx = useContext(ConsensusStatusContext)
  if (!ctx) {
    throw new Error('useConsensusStatusContext requires ConsensusStatusProvider')
  }
  return ctx
}
