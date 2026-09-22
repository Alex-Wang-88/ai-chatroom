import type { Conversation } from '../types'
import { NavLink } from 'react-router-dom'

export function ConversationSidebar({ conversations, currentId, onSelect, onCreate }: { conversations: Conversation[]; currentId: string | null; onSelect: (id: string) => void; onCreate: () => void }) {
  return <aside className="sidebar">
    <div className="brand"><div className="brand-mark">✦</div><div><strong>AI 聊天室</strong><span>多模型群聊</span></div></div>
    <button className="new-chat" onClick={onCreate}>＋ 新建聊天</button>
    <NavLink className={({ isActive }) => `debate-nav-link ${isActive ? 'active' : ''}`} to="/" end>◈ 聊天室</NavLink>
    <NavLink className={({ isActive }) => `debate-nav-link ${isActive ? 'active' : ''}`} to="/debate">⚖ AI 辩论</NavLink>
    <div className="sidebar-label">历史聊天</div>
    <div className="conversation-list">
      {conversations.map((conversation) => <button key={conversation.id} className={`conversation-item ${conversation.id === currentId ? 'active' : ''}`} onClick={() => onSelect(conversation.id)}><span className="conversation-icon">{conversation.mode === 'free' ? '◌' : '◈'}</span><span>{conversation.title}</span></button>)}
      {!conversations.length && <div className="empty-sidebar">创建第一个聊天室</div>}
    </div>
    <div className="sidebar-footer">V0.1 · 纯文字</div>
  </aside>
}
