import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MessageBubble } from './MessageBubble'

const message = {
  id: 'message-1',
  conversation_id: 'conversation-1',
  round_id: 'round-1',
  sender_type: 'agent' as const,
  sender_id: 'agent-1',
  sender_display_name: 'qwen36flash',
  content: '### 标题\n\n- **重点**：内容\n- **“中文重点”**\n- `代码`\n\n[文档](https://example.com/docs)',
  status: 'completed' as const,
  display_sequence: 1,
  created_at: '2026-09-01T00:00:00Z',
  first_token_at: '2026-09-01T00:00:01Z',
  finished_at: '2026-09-01T00:00:02Z',
}

describe('MessageBubble markdown rendering', () => {
  it('renders common markdown instead of showing syntax literally', () => {
    const { container } = render(<MessageBubble message={message} />)

    expect(screen.getByRole('heading', { name: '标题', level: 3 })).toBeInTheDocument()
    expect(container.querySelector('strong')).toHaveTextContent('重点')
    expect(container.querySelectorAll('strong')[1]).toHaveTextContent('中文重点')
    expect(container.querySelector('code')).toHaveTextContent('代码')
    expect(screen.getByRole('link', { name: '文档' })).toHaveAttribute('target', '_blank')
    expect(container.textContent).not.toContain('**')
  })
})
