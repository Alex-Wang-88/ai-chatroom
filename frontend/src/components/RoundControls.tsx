import { useRoundStore } from '../stores/roundStore'

export function RoundControls({ conversationId, mode }: { conversationId: string | null; mode: 'topic' | 'free' }) {
  const active = useRoundStore((state) => state.active)
  const readyForNext = useRoundStore((state) => state.readyForNext)
  const loading = useRoundStore((state) => state.loading)
  const next = useRoundStore((state) => state.next)
  const stop = useRoundStore((state) => state.stop)
  if (!conversationId) return null
  return <div className="round-controls">
    {active && <><span className="round-running"><span className="pulse-dot" />第 {active.round_number} 轮进行中</span><button className="stop-button" onClick={() => void stop()}>停止讨论</button></>}
    {!active && readyForNext && mode === 'topic' && <button className="next-button" disabled={loading} onClick={() => void next(conversationId)}>下一步 <span>→</span></button>}
  </div>
}
