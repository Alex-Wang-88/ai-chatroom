import { create } from 'zustand'
import { api } from '../api/client'
import type { ConversationAgent, EventEnvelope } from '../types'

interface AgentState {
  members: ConversationAgent[]
  activity: Record<string, Record<string, unknown>>
  load: (conversationId: string) => Promise<void>
  toggleMute: (conversationId: string, agentId: string, muted: boolean) => Promise<void>
  applyEvent: (event: EventEnvelope) => void
}

export const useAgentStore = create<AgentState>((set) => ({
  members: [], activity: {},
  load: async (conversationId) => set({ members: await api.agents(conversationId) }),
  toggleMute: async (conversationId, agentId, muted) => {
    const updated = await api.mute(conversationId, agentId, muted)
    set((state) => ({ members: state.members.map((member) => member.agent.id === agentId ? updated : member) }))
  },
  applyEvent: (event) => {
    if (event.type === 'conversation_agent.updated') {
      const p = event.payload
      set((state) => ({ members: state.members.map((member) => member.agent.id === p.agent_id ? { ...member, muted: Boolean(p.muted), enabled: Boolean(p.enabled ?? member.enabled), sort_order: Number(p.sort_order ?? member.sort_order) } : member) }))
    }
    if (event.type === 'agent.state_changed') {
      set((state) => ({ activity: { ...state.activity, [String(event.payload.agent_id)]: event.payload } }))
    }
  },
}))
