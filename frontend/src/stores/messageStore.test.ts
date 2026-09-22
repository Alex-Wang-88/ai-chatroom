import { beforeEach, describe, expect, it } from 'vitest'
import { useMessageStore } from './messageStore'
import type { EventEnvelope } from '../types'

const event = (type: string, payload: Record<string, unknown>, sequence: number): EventEnvelope => ({
  protocol_version: 1, type, stream_epoch: 'test', sequence, occurred_at: new Date().toISOString(), conversation_id: 'c', payload,
})

describe('messageStore', () => {
  beforeEach(() => useMessageStore.getState().reset())

  it('keeps multiple streams and stable display order', () => {
    const store = useMessageStore.getState()
    store.applyEvent(event('message.created', { message_id: 'slow', agent_id: 'a', sender_display_name: '慢', display_sequence: 2, content: 'S', status: 'streaming' }, 1))
    store.applyEvent(event('message.created', { message_id: 'fast', agent_id: 'b', sender_display_name: '快', display_sequence: 1, content: 'F', status: 'streaming' }, 2))
    store.applyEvent(event('message.delta', { message_id: 'slow', agent_id: 'a', delta: '2', delta_index: 1 }, 3))
    store.applyEvent(event('message.delta', { message_id: 'fast', agent_id: 'b', delta: '!', delta_index: 1 }, 4))
    expect(useMessageStore.getState().order).toEqual(['fast', 'slow'])
    expect(useMessageStore.getState().byId.slow.content).toBe('S2')
    expect(useMessageStore.getState().byId.fast.content).toBe('F!')
  })

  it('ignores duplicate deltas', () => {
    const store = useMessageStore.getState()
    store.applyEvent(event('message.created', { message_id: 'm', agent_id: 'a', display_sequence: 1, content: 'A', status: 'streaming' }, 1))
    store.applyEvent(event('message.delta', { message_id: 'm', delta: 'B', delta_index: 1 }, 2))
    store.applyEvent(event('message.delta', { message_id: 'm', delta: 'B', delta_index: 1 }, 3))
    expect(useMessageStore.getState().byId.m.content).toBe('AB')
  })
})
