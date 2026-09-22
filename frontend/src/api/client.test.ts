import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'
import type { DebateResponseRequest } from '../types'

const payload: DebateResponseRequest = {
  debate_id: 'debate-1',
  topic: '地球是不是圆的？',
  pro_position: null,
  con_position: null,
  pro_agent_id: 'agent-pro',
  con_agent_id: 'agent-con',
  side: 'pro',
  history: [],
}

describe('debate streaming client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('parses fragmented SSE blocks and forwards deltas immediately', async () => {
    const encoder = new TextEncoder()
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('event: start\ndata: {"side":"pro"}\n\nevent: delta\ndata: {"text":"你好"}\n'))
        controller.enqueue(encoder.encode('\nevent: delta\ndata: {"text":"世界"}\n\n'))
        controller.enqueue(encoder.encode('event: done\ndata: {"side":"pro","content":"你好世界","agent_id":"agent-pro","display_name":"deepseekv4lash","model_id":"deep"}\n\n'))
        controller.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })))
    const deltas: string[] = []

    const response = await api.debateRespondStream(payload, (text) => deltas.push(text))

    expect(deltas).toEqual(['你好', '世界'])
    expect(response.content).toBe('你好世界')
    expect(response.side).toBe('pro')
  })
})
