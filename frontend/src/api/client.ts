import type { Agent, Conversation, ConversationAgent, DebateCreateRequest, DebateRecord, DebateResponse, DebateResponseRequest, DebateSummary, Message, Round } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000/api/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail?.detail?.message ?? `请求失败 (${response.status})`)
  }
  return response.json() as Promise<T>
}

function parseSseBlock(block: string): { event: string; data: Record<string, unknown> } | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }
  if (!dataLines.length) return null
  return { event, data: JSON.parse(dataLines.join('\n')) as Record<string, unknown> }
}

export const api = {
  conversations: () => request<Conversation[]>('/conversations'),
  conversation: (id: string) => request<Conversation>(`/conversations/${id}`),
  updateConversation: (id: string, patch: Partial<Pick<Conversation, 'mode' | 'title' | 'free_max_messages'>>) => request<Conversation>(`/conversations/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  createConversation: (mode: 'topic' | 'free' = 'topic') => request<Conversation>('/conversations', { method: 'POST', body: JSON.stringify({ mode }) }),
  messages: (id: string) => request<Message[]>(`/conversations/${id}/messages`),
  agents: (id: string) => request<ConversationAgent[]>(`/conversations/${id}/agents`),
  availableAgents: () => request<Agent[]>('/agents'),
  debates: () => request<DebateSummary[]>('/debates'),
  debate: (id: string) => request<DebateRecord>(`/debates/${id}`),
  createDebate: (payload: DebateCreateRequest) => request<DebateRecord>('/debates', { method: 'POST', body: JSON.stringify(payload) }),
  renameDebate: (id: string, title: string) => request<DebateSummary>(`/debates/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  endDebate: (id: string) => request<DebateSummary>(`/debates/${id}/end`, { method: 'POST' }),
  sendMessage: (id: string, content: string) => request<{ message: Message; round: Round }>(`/conversations/${id}/messages`, { method: 'POST', body: JSON.stringify({ content, client_message_id: crypto.randomUUID() }) }),
  debateRespond: (payload: DebateResponseRequest) => request<DebateResponse>('/debates/respond', { method: 'POST', body: JSON.stringify(payload) }),
  debateRespondStream: async (payload: DebateResponseRequest, onDelta: (text: string) => void): Promise<DebateResponse> => {
    const response = await fetch(`${API_BASE}/debates/respond/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}))
      throw new Error(detail?.detail?.message ?? `请求失败 (${response.status})`)
    }
    if (!response.body) throw new Error('浏览器不支持流式响应')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let pending = ''
    let finalResponse: DebateResponse | null = null
    const processBlock = (block: string) => {
      const parsed = parseSseBlock(block)
      if (!parsed) return
      if (parsed.event === 'delta' && typeof parsed.data.text === 'string') onDelta(parsed.data.text)
      if (parsed.event === 'done') finalResponse = parsed.data as unknown as DebateResponse
      if (parsed.event === 'error') throw new Error(String(parsed.data.message ?? '模型响应失败，请重试'))
    }

    try {
      while (true) {
        const { done, value } = await reader.read()
        pending += decoder.decode(value, { stream: !done })
        const blocks = pending.split(/\r?\n\r?\n/)
        pending = blocks.pop() ?? ''
        for (const block of blocks) processBlock(block)
        if (done) {
          if (pending.trim()) processBlock(pending)
          break
        }
      }
    } catch (error) {
      await reader.cancel().catch(() => undefined)
      throw error
    }

    if (!finalResponse) throw new Error('流式响应未正常结束')
    return finalResponse
  },
  nextRound: (id: string) => request<Round>(`/conversations/${id}/rounds/next`, { method: 'POST', body: JSON.stringify({ idempotency_key: crypto.randomUUID() }) }),
  stopRound: (roundId: string) => request(`/rounds/${roundId}/cancel`, { method: 'POST' }),
  mute: (conversationId: string, agentId: string, muted: boolean) => request<ConversationAgent>(`/conversations/${conversationId}/agents/${agentId}`, { method: 'PATCH', body: JSON.stringify({ muted }) }),
  retry: (messageId: string) => request(`/messages/${messageId}/retry`, { method: 'POST' }),
  activeRun: (id: string) => request<{ round: Round | null; messages: Message[]; agent_states: Record<string, unknown> }>(`/conversations/${id}/active-run`),
}

export function websocketUrl(conversationId: string, afterSequence: number): string {
  const base = API_BASE.replace(/^http/, 'ws').replace(/\/api\/v1$/, '')
  return `${base}/api/v1/ws/v1/conversations/${conversationId}?after_sequence=${afterSequence}`
}
