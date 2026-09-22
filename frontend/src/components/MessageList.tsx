import { useMemo } from 'react'
import { useMessageStore } from '../stores/messageStore'
import { MessageBubble } from './MessageBubble'

export function MessageList() {
  const byId = useMessageStore((state) => state.byId)
  const order = useMessageStore((state) => state.order)
  const messages = useMemo(() => order.map((id) => byId[id]).filter(Boolean), [byId, order])
  return <div className="message-list" aria-live="polite">
    {!messages.length && <div className="welcome-state"><div className="welcome-orbit">✦</div><h2>让不同的 AI 坐到同一张桌子</h2><p>提出一个问题，观察他们同时思考、回应和碰撞。</p></div>}
    {messages.map((message) => <MessageBubble key={message.id} message={message} />)}
  </div>
}
