import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import type { Agent, DebateRecord, DebateResponse } from '../types'
import { DebatePage } from './DebatePage'

const models: Agent[] = [
  {
    id: 'agent-pro', display_name: 'deepseekv4lash', mention_handle: 'deepseekv4lash', mention_aliases: [],
    avatar: null, provider: 'jimo', model_id: 'deep', system_prompt: '', talkativeness: 1,
    temperature: null, max_output_tokens: null, enabled: true,
  },
  {
    id: 'agent-con', display_name: 'qwen36flash', mention_handle: 'qwen36flash', mention_aliases: [],
    avatar: null, provider: 'jimo', model_id: 'qwen', system_prompt: '', talkativeness: 1,
    temperature: null, max_output_tokens: null, enabled: true,
  },
]

const proResponse: DebateResponse = { side: 'pro', content: '正方开篇立论。', agent_id: 'agent-pro', display_name: 'deepseekv4lash', model_id: 'deep' }
const conResponse: DebateResponse = { side: 'con', content: '反方回应。', agent_id: 'agent-con', display_name: 'qwen36flash', model_id: 'qwen' }
const createdRecord: DebateRecord = {
  id: 'debate-1', title: '大学生是否应该使用短视频？', topic: '大学生是否应该使用短视频？',
  pro_position: null, con_position: null, pro_agent_id: 'agent-pro', con_agent_id: 'agent-con',
  status: 'active', turn_count: 0, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  ended_at: null, turns: [],
}
const savedRecord: DebateRecord = {
  ...createdRecord,
  title: '保存的辩论',
  turn_count: 1,
  turns: [{ side: 'pro', content: '已保存的正方观点。', agent_id: 'agent-pro', display_name: 'deepseekv4lash', model_id: 'deep' }],
}

describe('DebatePage', () => {
  beforeEach(() => {
    vi.spyOn(api, 'availableAgents').mockResolvedValue(models)
    vi.spyOn(api, 'debates').mockResolvedValue([])
    vi.spyOn(api, 'createDebate').mockResolvedValue(createdRecord)
    vi.spyOn(api, 'debateRespondStream').mockImplementation(async (payload, onDelta) => {
      const response = payload.side === 'pro' ? proResponse : conResponse
      onDelta(response.content)
      return response
    })
  })

  afterEach(() => vi.restoreAllMocks())

  it('starts with pro and manually advances to con', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={['/debate']}><DebatePage /></MemoryRouter>)

    const topic = await screen.findByPlaceholderText(/请输入明确的可争论命题/)
    await user.type(topic, '大学生是否应该使用短视频？')
    await user.click(screen.getByRole('button', { name: /开始辩论/ }))

    await waitFor(() => expect(api.debateRespondStream).toHaveBeenCalledTimes(1))
    expect(api.debateRespondStream).toHaveBeenLastCalledWith(expect.objectContaining({ side: 'pro', history: [] }), expect.any(Function))
    expect(screen.getByText('正方开篇立论。')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /让反方发言/ }))
    await waitFor(() => expect(api.debateRespondStream).toHaveBeenCalledTimes(2))
    expect(api.debateRespondStream).toHaveBeenLastCalledWith(expect.objectContaining({
      side: 'con',
      history: [{ side: 'pro', content: '正方开篇立论。' }],
    }), expect.any(Function))
    expect(screen.getByText('反方回应。')).toBeInTheDocument()
  })

  it('loads a saved debate and renames its history entry', async () => {
    const user = userEvent.setup()
    vi.mocked(api.debates).mockResolvedValue([{
      id: savedRecord.id, title: savedRecord.title, topic: savedRecord.topic,
      pro_position: savedRecord.pro_position, con_position: savedRecord.con_position,
      pro_agent_id: savedRecord.pro_agent_id, con_agent_id: savedRecord.con_agent_id,
      status: savedRecord.status, turn_count: savedRecord.turn_count,
      created_at: savedRecord.created_at, updated_at: savedRecord.updated_at, ended_at: savedRecord.ended_at,
    }])
    vi.spyOn(api, 'debate').mockResolvedValue(savedRecord)
    vi.spyOn(api, 'renameDebate').mockResolvedValue({
      id: savedRecord.id, title: '改过的名称', topic: savedRecord.topic,
      pro_position: savedRecord.pro_position, con_position: savedRecord.con_position,
      pro_agent_id: savedRecord.pro_agent_id, con_agent_id: savedRecord.con_agent_id,
      status: savedRecord.status, turn_count: savedRecord.turn_count,
      created_at: savedRecord.created_at, updated_at: '2026-01-01T00:01:00Z', ended_at: savedRecord.ended_at,
    })
    render(<MemoryRouter initialEntries={['/debate']}><DebatePage /></MemoryRouter>)

    const savedDebateButtons = await screen.findAllByRole('button', { name: /保存的辩论/ })
    await user.click(savedDebateButtons[0])
    await waitFor(() => expect(api.debate).toHaveBeenCalledWith('debate-1'))
    expect(screen.getByText('已保存的正方观点。')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /重命名 保存的辩论/ }))
    const renameInput = screen.getByRole('textbox', { name: '记录名称' })
    await user.clear(renameInput)
    await user.type(renameInput, '改过的名称')
    await user.click(screen.getByRole('button', { name: '保存名称' }))

    await waitFor(() => expect(api.renameDebate).toHaveBeenCalledWith('debate-1', '改过的名称'))
    expect(screen.getByText('改过的名称')).toBeInTheDocument()
  })
})
