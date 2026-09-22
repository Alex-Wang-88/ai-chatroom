import { useEffect, useMemo, useState } from 'react'
import { api, websocketUrl } from '../api/client'
import { useConversationStore } from '../stores/conversationStore'
import { useMessageStore } from '../stores/messageStore'
import { useAgentStore } from '../stores/agentStore'
import { useRoundStore } from '../stores/roundStore'
import type { EventEnvelope } from '../types'
import { ConversationSidebar } from '../components/ConversationSidebar'
import { MessageList } from '../components/MessageList'
import { Composer } from '../components/Composer'
import { MemberList } from '../components/MemberList'
import { RoundControls } from '../components/RoundControls'
import { standardModelName } from '../utils/modelNames'

const freeStopReasonLabels: Record<string, string> = {
  cycle_limit: '已完成两轮讨论',
  max_messages: '达到消息上限',
  no_eligible_speaker: '没有可发言的成员',
  error_threshold: '连续出错，已自动停止',
  user_stopped: '已手动停止',
  conversation_closed: '会话已关闭',
}

export function ChatRoomPage() {
  const { conversations, currentId, create, select } = useConversationStore()
  const current = conversations.find((conversation) => conversation.id === currentId)
  const loadMessages = useMessageStore((state) => state.load)
  const resetMessages = useMessageStore((state) => state.reset)
  const applyMessageEvent = useMessageStore((state) => state.applyEvent)
  const needsSync = useMessageStore((state) => state.needsSync)
  const clearSync = useMessageStore((state) => state.clearSync)
  const lastSequence = useMessageStore((state) => state.lastSequence)
  const loadAgents = useAgentStore((state) => state.load)
  const applyAgentEvent = useAgentStore((state) => state.applyEvent)
  const setRound = useRoundStore((state) => state.setActive)
  const markStarted = useRoundStore((state) => state.markStarted)
  const markCompleted = useRoundStore((state) => state.markCompleted)
  const [socketState, setSocketState] = useState<'connecting' | 'connected' | 'offline'>('offline')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    if (!currentId) return
    resetMessages()
    void Promise.all([loadMessages(currentId), loadAgents(currentId), api.activeRun(currentId).then((active) => setRound(active.round))])
  }, [currentId, loadAgents, loadMessages, resetMessages, setRound])

  useEffect(() => {
    if (!currentId || !needsSync) return
    clearSync()
    void loadMessages(currentId)
  }, [clearSync, currentId, loadMessages, needsSync])

  useEffect(() => {
    if (!currentId) return
    let socket: WebSocket | undefined
    let retryTimer: number | undefined
    let stopped = false
    let retryAttempt = 0
    const epochRef = { current: '' }
    const connect = () => {
      if (stopped) return
      setSocketState('connecting')
      socket = new WebSocket(websocketUrl(currentId, useMessageStore.getState().lastSequence))
      socket.onopen = () => { retryAttempt = 0; setSocketState('connected') }
      socket.onmessage = (raw) => {
        const event = JSON.parse(raw.data) as EventEnvelope
        if (event.type === 'connection.ready') {
          if (epochRef.current && epochRef.current !== event.stream_epoch) {
            // A changed epoch means the backend restarted and its ring buffer
            // is no longer a continuation of this client's sequence.
            resetMessages()
            void Promise.all([loadMessages(currentId), api.activeRun(currentId).then((active) => setRound(active.round))])
          }
          epochRef.current = event.stream_epoch
          return
        }
        if (event.type === 'sync.required') {
          void loadMessages(currentId)
          return
        }
        applyMessageEvent(event)
        applyAgentEvent(event)
        if (event.type === 'round.started') {
          void api.activeRun(currentId).then((active) => setRound(active.round))
        }
        if (event.type === 'round.completed' || event.type === 'round.cancelled') markCompleted()
        if (event.type === 'free_mode.started') {
          void api.activeRun(currentId).then((active) => { if (active.round) markStarted(active.round) })
        }
        if (event.type === 'free_mode.stopped') {
          const reason = freeStopReasonLabels[String(event.payload.stop_reason ?? '')] ?? '讨论结束'
          const generated = Number(event.payload.generated_messages ?? 0)
          setNotice(`自由模式${reason}（共 ${Number.isFinite(generated) ? generated : 0} 条 AI 发言）`)
        }
        if (event.type === 'warning.mention_rejected') {
          const agents = Array.isArray(event.payload.agents) ? event.payload.agents.map((agent) => standardModelName(String(agent))).join('、') : '该成员'
          setNotice(`提示：${agents} 当前不可参与`)
        }
      }
      socket.onclose = () => {
        setSocketState('offline')
        if (!stopped) {
          const baseDelay = Math.min(10000, 500 * (2 ** retryAttempt))
          retryAttempt += 1
          const jitteredDelay = baseDelay * (0.8 + Math.random() * 0.4)
          retryTimer = window.setTimeout(connect, jitteredDelay)
        }
      }
      socket.onerror = () => socket?.close()
    }
    connect()
    return () => { stopped = true; if (retryTimer) window.clearTimeout(retryTimer); socket?.close() }
  }, [applyAgentEvent, applyMessageEvent, currentId, loadMessages, markCompleted, markStarted, resetMessages, setRound])

  const send = async (content: string) => {
    if (!currentId) return
    setNotice('')
    try { const result = await api.sendMessage(currentId, content); setRound(result.round) }
    catch (error) { setNotice(error instanceof Error ? error.message : '发送失败') }
  }

  const newConversation = async (mode: 'topic' | 'free' = 'topic') => { await create(mode) }
  const changeMode = async (mode: 'topic' | 'free') => { if (currentId) await api.updateConversation(currentId, { mode }); await useConversationStore.getState().load() }
  const modeLabel = useMemo(() => current?.mode === 'free' ? '自由模式' : '话题模式', [current?.mode])

  return (
    <main className="app-shell">
      <ConversationSidebar conversations={conversations} currentId={currentId} onSelect={select} onCreate={() => void newConversation()} />
      <section className="room-panel">
        <header className="room-header">
          <div><span className="eyebrow">AI CHAT ROOM</span><h1>{current?.title ?? 'AI 聊天室'}</h1></div>
          <div className="header-actions"><select className="mode-select" value={current?.mode ?? 'topic'} onChange={(event) => void changeMode(event.target.value as 'topic' | 'free')} aria-label="聊天模式"><option value="topic">话题模式</option><option value="free">自由模式</option></select><div className="connection-pill"><span className={`status-dot ${socketState}`} />{modeLabel}</div></div>
        </header>
        {notice && <div className="notice" role="status">{notice}<button onClick={() => setNotice('')}>×</button></div>}
        <MessageList />
        <RoundControls conversationId={currentId} mode={current?.mode ?? 'topic'} />
        <Composer onSend={send} />
      </section>
      <MemberList conversationId={currentId} />
    </main>
  )
}
