import { create } from 'zustand'
import { api } from '../api/client'
import type { EventEnvelope, Message } from '../types'

interface MessageState {
  byId: Record<string, Message>
  order: string[]
  lastSequence: number
  needsSync: boolean
  load: (conversationId: string) => Promise<void>
  applyEvent: (event: EventEnvelope) => void
  reset: () => void
  clearSync: () => void
}

function insertOrder(order: string[], message: Message, byId: Record<string, Message>): string[] {
  if (order.includes(message.id)) return order
  const result = [...order, message.id]
  return result.sort((a, b) => {
    const left = byId[a]?.display_sequence ?? Number.MAX_SAFE_INTEGER
    const right = byId[b]?.display_sequence ?? Number.MAX_SAFE_INTEGER
    return left - right
  })
}

export const useMessageStore = create<MessageState>((set) => ({
  byId: {}, order: [], lastSequence: 0, needsSync: false,
  load: async (conversationId) => {
    const messages = await api.messages(conversationId)
    set((state) => {
      const byId = { ...state.byId }
      for (const message of messages) {
        const previous = byId[message.id]
        // A REST snapshot can race a newer WebSocket delta. Preserve the
        // longer in-memory buffer and its streaming status in that case.
        if (previous && previous.content.length > message.content.length) {
          byId[message.id] = { ...message, ...previous, display_sequence: message.display_sequence ?? previous.display_sequence }
        } else {
          byId[message.id] = { ...previous, ...message }
        }
      }
      const order = Object.values(byId)
        .filter((message) => message.conversation_id === conversationId)
        .sort((a, b) => (a.display_sequence ?? Number.MAX_SAFE_INTEGER) - (b.display_sequence ?? Number.MAX_SAFE_INTEGER))
        .map((message) => message.id)
      return { byId, order, needsSync: false }
    })
  },
  applyEvent: (event) => {
    set((state) => {
      const p = event.payload
      const id = String(p.message_id ?? '')
      if (!id) return { lastSequence: Math.max(state.lastSequence, event.sequence) }
      const previous = state.byId[id]
      const sender = String(p.sender_display_name ?? previous?.sender_display_name ?? 'AI')
      const next: Message = {
        id,
        conversation_id: event.conversation_id,
        round_id: (p.round_id as string | null) ?? previous?.round_id ?? null,
        sender_type: 'agent', sender_id: (p.agent_id as string | null) ?? previous?.sender_id ?? null,
        sender_display_name: sender,
        content: String(p.content ?? previous?.content ?? ''),
        status: (p.status as Message['status']) ?? previous?.status ?? 'pending',
        display_sequence: (p.display_sequence as number | null) ?? previous?.display_sequence ?? null,
        created_at: previous?.created_at ?? event.occurred_at,
        first_token_at: previous?.first_token_at ?? null,
        finished_at: previous?.finished_at ?? null,
      }
      let needsSync = state.needsSync
      if (event.type === 'message.delta') {
        const deltaIndex = Number(p.delta_index ?? 0)
        const previousIndex = Number((previous as Message & { deltaIndex?: number } | undefined)?.deltaIndex ?? 0)
        const cumulativeLength = Number(p.cumulative_length ?? 0)
        if (deltaIndex <= previousIndex || (cumulativeLength > 0 && previous && previous.content.length >= cumulativeLength)) return { lastSequence: Math.max(state.lastSequence, event.sequence) }
        if (previousIndex > 0 && deltaIndex > previousIndex + 1) needsSync = true
        next.content = `${previous?.content ?? ''}${String(p.delta ?? '')}`
        ;(next as Message & { deltaIndex?: number }).deltaIndex = deltaIndex
        next.status = 'streaming'
      }
      if (event.type === 'message.created') {
        if (p.delta_index !== undefined) {
          ;(next as Message & { deltaIndex?: number }).deltaIndex = Number(p.delta_index)
        }
      }
      if (event.type === 'message.completed') next.status = 'completed'
      if (event.type === 'message.error') next.status = 'error'
      if (event.type === 'message.cancelled') next.status = 'cancelled'
      const byId = { ...state.byId, [id]: next }
      return { byId, order: insertOrder(state.order, next, byId), lastSequence: Math.max(state.lastSequence, event.sequence), needsSync }
    })
  },
  reset: () => set({ byId: {}, order: [], lastSequence: 0, needsSync: false }),
  clearSync: () => set({ needsSync: false }),
}))
