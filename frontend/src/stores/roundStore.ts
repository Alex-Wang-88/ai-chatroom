import { create } from 'zustand'
import { api } from '../api/client'
import type { Round } from '../types'

interface RoundState {
  active: Round | null
  readyForNext: boolean
  loading: boolean
  setActive: (round: Round | null) => void
  markStarted: (round: Round) => void
  markCompleted: () => void
  next: (conversationId: string) => Promise<void>
  stop: () => Promise<void>
}

export const useRoundStore = create<RoundState>((set, get) => ({
  active: null, readyForNext: false, loading: false,
  setActive: (active) => set({ active, readyForNext: false }),
  markStarted: (active) => set({ active, readyForNext: false }),
  markCompleted: () => set({ active: null, readyForNext: true }),
  next: async (conversationId) => { set({ loading: true, readyForNext: false }); try { set({ active: await api.nextRound(conversationId) }) } finally { set({ loading: false }) } },
  stop: async () => { const round = get().active; if (round) await api.stopRound(round.id) },
}))
