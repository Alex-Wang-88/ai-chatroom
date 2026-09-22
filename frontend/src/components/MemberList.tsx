import { useAgentStore } from '../stores/agentStore'
import { standardAgentName } from '../utils/modelNames'

const activityLabel: Record<string, string> = { idle: '空闲', thinking: '思考中', streaming: '正在输出', error: '请求失败', cancelled: '已取消' }

export function MemberList({ conversationId }: { conversationId: string | null }) {
  const members = useAgentStore((state) => state.members)
  const activity = useAgentStore((state) => state.activity)
  const toggleMute = useAgentStore((state) => state.toggleMute)
  return <aside className="member-panel"><div className="member-heading"><div><span className="eyebrow">ROOM MEMBERS</span><h2>群聊成员</h2></div><span className="member-count">{members.length + 1}</span></div><div className="member-list"><div className="member-row user-member"><div className="avatar user-avatar">你</div><div className="member-copy"><strong>用户</strong><span>主持人</span></div><span className="online-dot" /></div>{members.map((member) => { const state = activity[member.agent.id]; const current = String(state?.activity ?? 'idle'); const muted = member.muted; const displayName = standardAgentName(member.agent.mention_handle, member.agent.display_name); return <div className={`member-row ${muted ? 'muted' : ''}`} key={member.agent.id}><div className="avatar agent-avatar">{displayName.slice(0, 1)}</div><div className="member-copy"><strong>{displayName}</strong><span>{muted ? '已静音' : activityLabel[current] ?? '空闲'}</span></div><button className="mute-button" title={muted ? '取消静音' : '静音'} onClick={() => conversationId && void toggleMute(conversationId, member.agent.id, !muted)}>{muted ? '🔇' : '🎙'}</button></div> })}</div><div className="member-note">静音只影响新的讨论，不会删除历史消息。</div></aside>
}
