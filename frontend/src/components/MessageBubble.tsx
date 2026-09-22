import type { Message } from '../types'
import { api } from '../api/client'
import { standardModelName } from '../utils/modelNames'
import { prepareMarkdown } from '../utils/markdown'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.sender_type === 'user'
  const displayName = isUser ? message.sender_display_name : standardModelName(message.sender_display_name)
  const statusLabel = message.status === 'streaming' ? '正在输出' : message.status === 'pending' ? '思考中' : message.status === 'error' ? '请求失败' : message.status === 'cancelled' ? '已取消' : ''
  return <article className={`message-row ${isUser ? 'user-row' : 'agent-row'}`} data-message-id={message.id}>
    {!isUser && <div className="avatar agent-avatar">{displayName.slice(0, 1)}</div>}
    <div className="message-stack">
      <div className="message-meta"><span className="sender-name">{displayName}</span>{statusLabel && <span className={`message-status ${message.status}`}>{statusLabel}{message.status === 'streaming' && <span className="cursor" />}</span>}</div>
      <div className={`message-bubble ${isUser ? 'user-bubble' : 'agent-bubble'} ${message.status}`}>
        {message.content ? <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            // Keep links useful without allowing an AI response to navigate
            // the current app tab away from the room.
            a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
          }}
        >{prepareMarkdown(message.content)}</ReactMarkdown> : (message.status === 'pending' ? '…' : '')}
      </div>
      {(message.status === 'error' || message.status === 'cancelled') && <button className="retry-button" onClick={() => void api.retry(message.id)}>↻ 重试</button>}
    </div>
  </article>
}
