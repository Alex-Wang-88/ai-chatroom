import { create } from 'zustand'
import { api } from '../api/client'
import type { Conversation } from '../types'

interface ConversationState {
  conversations: Conversation[]
  currentId: string | null
  loading: boolean
  load: () => Promise<void>
  create: (mode?: 'topic' | 'free') => Promise<Conversation>
  select: (id: string) => void
}

export const useConversationStore = create<ConversationState>((set, get) => ({
  conversations: [], currentId: null, loading: false,
  load: async () => {
    set({ loading: true })
    try {
      const conversations = await api.conversations()
      set({ conversations, currentId: get().currentId ?? conversations[0]?.id ?? null })
    } finally { set({ loading: false }) }
  },
  create: async (mode = 'topic') => {
    const conversation = await api.createConversation(mode)
    set((state) => ({ conversations: [conversation, ...state.conversations], currentId: conversation.id }))
    return conversation
  },
  select: (id) => set({ currentId: id }),
}))
