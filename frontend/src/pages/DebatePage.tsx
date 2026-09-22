import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../api/client'
import type { Agent, DebateCreateRequest, DebateInputMode, DebateRecord, DebateResponseRequest, DebateSide, DebateSummary, DebateTurn } from '../types'
import { standardAgentName } from '../utils/modelNames'
import { prepareMarkdown } from '../utils/markdown'

const TITLE_MAX_LENGTH = 200
const TOPIC_MAX_LENGTH = 200
const POSITION_MAX_LENGTH = 500

function sideLabel(side: DebateSide): string {
  return side === 'pro' ? '正方' : '反方'
}

function modelLabel(agent: Agent): string {
  return standardAgentName(agent.mention_handle, agent.display_name)
}

function recordSummary(record: DebateRecord): DebateSummary {
  const { turns: _turns, ...summary } = record
  return summary
}

export function DebatePage() {
  const [models, setModels] = useState<Agent[]>([])
  const [records, setRecords] = useState<DebateSummary[]>([])
  const [mode, setMode] = useState<DebateInputMode>('topic')
  const [title, setTitle] = useState('')
  const [topic, setTopic] = useState('')
  const [proPosition, setProPosition] = useState('')
  const [conPosition, setConPosition] = useState('')
  const [proAgentId, setProAgentId] = useState('')
  const [conAgentId, setConAgentId] = useState('')
  const [debateId, setDebateId] = useState('')
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [turns, setTurns] = useState<DebateTurn[]>([])
  const [started, setStarted] = useState(false)
  const [ended, setEnded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadingRecordId, setLoadingRecordId] = useState<string | null>(null)
  const [loadingSide, setLoadingSide] = useState<DebateSide | null>(null)
  const [notice, setNotice] = useState('')

  useEffect(() => {
    let active = true
    void Promise.all([api.availableAgents(), api.debates()]).then(([available, saved]) => {
      if (!active) return
      const enabled = available.filter((agent) => agent.enabled)
      setModels(enabled)
      setRecords(saved)
      if (enabled.length) {
        setProAgentId((current) => current || enabled[0].id)
        setConAgentId((current) => current || enabled[1]?.id || enabled[0].id)
      }
    }).catch((error) => {
      if (active) setNotice(error instanceof Error ? error.message : '辩论记录或模型列表加载失败')
    })
    return () => { active = false }
  }, [])

  const proAgent = useMemo(() => models.find((agent) => agent.id === proAgentId), [models, proAgentId])
  const conAgent = useMemo(() => models.find((agent) => agent.id === conAgentId), [models, conAgentId])
  const busy = loading || Boolean(loadingRecordId)
  const locked = started || busy
  const nextSide: DebateSide = turns.length % 2 === 0 ? 'pro' : 'con'
  const inputValid = mode === 'topic'
    ? Boolean(topic.trim())
    : Boolean(proPosition.trim() && conPosition.trim())
  const canStart = Boolean(models.length && proAgentId && conAgentId && inputValid && !started && !ended && !busy)

  const rememberRecord = (summary: DebateSummary) => {
    setRecords((current) => [summary, ...current.filter((record) => record.id !== summary.id)])
  }

  const updateRecord = (summary: DebateSummary) => {
    setRecords((current) => current.map((record) => record.id === summary.id ? summary : record))
  }

  const buildPayload = (id: string, side: DebateSide, history: DebateTurn[]): DebateResponseRequest => ({
    debate_id: id,
    topic: mode === 'topic' ? topic.trim() : null,
    pro_position: mode === 'positions' ? proPosition.trim() : null,
    con_position: mode === 'positions' ? conPosition.trim() : null,
    pro_agent_id: proAgentId,
    con_agent_id: conAgentId,
    side,
    history: history.map((turn) => ({ side: turn.side, content: turn.content })),
  })

  const askSide = async (side: DebateSide, history: DebateTurn[], activeDebateId: string) => {
    const selectedAgent = side === 'pro' ? proAgent : conAgent
    if (!selectedAgent) {
      setNotice(`请先选择${sideLabel(side)}模型`)
      return
    }
    const pendingTurn: DebateTurn = {
      side,
      content: '',
      agent_id: selectedAgent.id,
      display_name: selectedAgent.display_name,
      model_id: selectedAgent.model_id,
    }
    let streamedContent = ''
    setLoading(true)
    setLoadingSide(side)
    setStarted(true)
    setTurns([...history, pendingTurn])
    setNotice('')
    try {
      const response = await api.debateRespondStream(buildPayload(activeDebateId, side, history), (delta) => {
        streamedContent += delta
        setTurns([...history, { ...pendingTurn, content: streamedContent }])
      })
      setTurns([...history, response])
      setRecords((current) => current.map((record) => record.id === activeDebateId ? {
        ...record,
        turn_count: Math.max(record.turn_count, history.length + 1),
        updated_at: new Date().toISOString(),
      } : record))
      setStarted(true)
      setEnded(false)
    } catch (error) {
      setTurns(history)
      if (!history.length) setStarted(false)
      setNotice(error instanceof Error ? error.message : '模型响应失败，请重试')
    } finally {
      setLoading(false)
      setLoadingSide(null)
    }
  }

  const startDebate = async () => {
    if (!models.length) {
      setNotice('暂时没有可用模型')
      return
    }
    if (!inputValid) {
      setNotice(mode === 'topic' ? '请先填写辩题' : '请完整填写正方和反方立场')
      return
    }
    if (!proAgentId || !conAgentId) {
      setNotice('请选择正方和反方模型')
      return
    }

    setNotice('')
    let activeDebateId = selectedRecordId
    if (!activeDebateId) {
      setLoading(true)
      setLoadingSide('pro')
      const payload: DebateCreateRequest = {
        title: title.trim() || null,
        topic: mode === 'topic' ? topic.trim() : null,
        pro_position: mode === 'positions' ? proPosition.trim() : null,
        con_position: mode === 'positions' ? conPosition.trim() : null,
        pro_agent_id: proAgentId,
        con_agent_id: conAgentId,
      }
      try {
        const created = await api.createDebate(payload)
        activeDebateId = created.id
        setDebateId(created.id)
        setSelectedRecordId(created.id)
        rememberRecord(recordSummary(created))
      } catch (error) {
        setLoading(false)
        setLoadingSide(null)
        setNotice(error instanceof Error ? error.message : '创建辩论记录失败，请重试')
        return
      }
    }

    if (activeDebateId) await askSide('pro', [], activeDebateId)
  }

  const nextTurn = () => {
    if (!started || ended || busy || !debateId) return
    void askSide(nextSide, turns, debateId)
  }

  const loadSavedDebate = async (id: string) => {
    if (busy) return
    setLoadingRecordId(id)
    setNotice('')
    try {
      const record = await api.debate(id)
      setSelectedRecordId(record.id)
      setDebateId(record.id)
      setTitle(record.title)
      setTopic(record.topic ?? '')
      setProPosition(record.pro_position ?? '')
      setConPosition(record.con_position ?? '')
      setMode(record.topic ? 'topic' : 'positions')
      setProAgentId(record.pro_agent_id)
      setConAgentId(record.con_agent_id)
      setTurns(record.turns)
      setStarted(record.turns.length > 0)
      setEnded(record.status === 'ended')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '辩论记录加载失败，请重试')
    } finally {
      setLoadingRecordId(null)
    }
  }

  const endCurrentDebate = async () => {
    if (!debateId || loading) return
    try {
      const updated = await api.endDebate(debateId)
      updateRecord(updated)
      setEnded(true)
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '结束辩论失败，请重试')
    }
  }

  const resetDebate = () => {
    setDebateId('')
    setSelectedRecordId(null)
    setTitle('')
    setTurns([])
    setStarted(false)
    setEnded(false)
    setNotice('')
  }

  const beginRename = (event: React.MouseEvent, record: DebateSummary) => {
    event.stopPropagation()
    if (busy) return
    setRenamingId(record.id)
    setRenameValue(record.title)
    setNotice('')
  }

  const cancelRename = () => {
    setRenamingId(null)
    setRenameValue('')
  }

  const saveRename = async () => {
    if (!renamingId) return
    const nextTitle = renameValue.trim()
    if (!nextTitle) {
      setNotice('记录名称不能为空')
      return
    }
    try {
      const updated = await api.renameDebate(renamingId, nextTitle)
      updateRecord(updated)
      if (selectedRecordId === updated.id) setTitle(updated.title)
      cancelRename()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '修改记录名称失败，请重试')
    }
  }

  const handleRenameKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      void saveRename()
    }
    if (event.key === 'Escape') cancelRename()
  }

  const displayTopic = mode === 'topic' ? topic.trim() : '自定义立场辩论'
  const statusText = loading
    ? `${sideLabel(loadingSide ?? nextSide)}正在发言`
    : ended
      ? '辩论已结束'
      : started
        ? `下一位：${sideLabel(nextSide)}`
        : '等待开始'

  return <main className="debate-shell">
    <header className="debate-header">
      <div className="debate-header-left">
        <Link className="back-link" to="/">← 返回聊天室</Link>
        <div><span className="eyebrow">AI DEBATE</span><h1>AI 辩论</h1></div>
      </div>
    </header>

    <div className="debate-layout">
      <aside className="debate-setup">
        <div className="debate-history">
          <div className="debate-history-heading"><span className="eyebrow">HISTORY</span><span>{records.length}</span></div>
          <div className="debate-history-list">
            {records.map((record) => renamingId === record.id ? <div className="debate-history-item editing" key={record.id}>
              <input
                autoFocus
                maxLength={TITLE_MAX_LENGTH}
                aria-label="记录名称"
                value={renameValue}
                onChange={(event) => setRenameValue(event.target.value)}
                onKeyDown={handleRenameKeyDown}
              />
              <div className="debate-history-edit-actions">
                <button aria-label="保存名称" onClick={() => void saveRename()}>✓</button>
                <button aria-label="取消重命名" onClick={cancelRename}>×</button>
              </div>
            </div> : <div className={`debate-history-item ${record.id === selectedRecordId ? 'active' : ''}`} key={record.id}>
              <button className="debate-history-select" disabled={busy} onClick={() => void loadSavedDebate(record.id)}>
                <strong title={record.title}>{record.title}</strong>
                <span>{record.turn_count} 次发言 · {record.status === 'ended' ? '已结束' : '进行中'}</span>
              </button>
              <button className="debate-history-rename" aria-label={`重命名 ${record.title}`} disabled={busy} onClick={(event) => beginRename(event, record)}>✎</button>
            </div>)}
            {!records.length && <div className="debate-history-empty">还没有保存的辩论</div>}
          </div>
        </div>

        <div className="debate-section-heading"><span className="eyebrow">SETUP</span><h2>辩论设置</h2></div>

        <label className="debate-field">
          <span className="debate-field-label">记录名称 <em>{title.length}/{TITLE_MAX_LENGTH}</em></span>
          <input value={title} maxLength={TITLE_MAX_LENGTH} disabled={locked} onChange={(event) => setTitle(event.target.value)} placeholder="可选，默认使用辩题作为名称" />
          <small>保存后也可以在上方历史记录中重命名。</small>
        </label>

        <div className="debate-mode-tabs" role="tablist" aria-label="辩论输入方式">
          <button className={mode === 'topic' ? 'active' : ''} role="tab" aria-selected={mode === 'topic'} disabled={locked} onClick={() => setMode('topic')}>按主题</button>
          <button className={mode === 'positions' ? 'active' : ''} role="tab" aria-selected={mode === 'positions'} disabled={locked} onClick={() => setMode('positions')}>按立场</button>
        </div>

        {mode === 'topic' ? <label className="debate-field">
          <span className="debate-field-label">辩题 <em>{topic.length}/{TOPIC_MAX_LENGTH}</em></span>
          <textarea value={topic} maxLength={TOPIC_MAX_LENGTH} disabled={locked} onChange={(event) => setTopic(event.target.value)} placeholder="请输入明确的可争论命题，例如：大学生是否应该使用短视频？" rows={4} />
          <small>正方支持该主题，反方反对该主题。</small>
        </label> : <>
          <label className="debate-field">
            <span className="debate-field-label"><i className="pro-dot" />正方立场 <em>{proPosition.length}/{POSITION_MAX_LENGTH}</em></span>
            <textarea value={proPosition} maxLength={POSITION_MAX_LENGTH} disabled={locked} onChange={(event) => setProPosition(event.target.value)} placeholder="请写清楚正方支持什么，以及适用范围。" rows={5} />
          </label>
          <label className="debate-field">
            <span className="debate-field-label"><i className="con-dot" />反方立场 <em>{conPosition.length}/{POSITION_MAX_LENGTH}</em></span>
            <textarea value={conPosition} maxLength={POSITION_MAX_LENGTH} disabled={locked} onChange={(event) => setConPosition(event.target.value)} placeholder="请写清楚反方反对什么，以及适用范围。" rows={5} />
          </label>
        </>}

        <div className="debate-models-heading"><span className="eyebrow">MODELS</span><span>可选择相同模型</span></div>
        <label className="debate-field model-field">
          <span className="debate-field-label"><i className="pro-dot" />正方模型</span>
          <select value={proAgentId} disabled={locked || !models.length} onChange={(event) => setProAgentId(event.target.value)}>
            <option value="">选择模型</option>
            {models.map((agent) => <option key={agent.id} value={agent.id}>{modelLabel(agent)}</option>)}
          </select>
        </label>
        <label className="debate-field model-field">
          <span className="debate-field-label"><i className="con-dot" />反方模型</span>
          <select value={conAgentId} disabled={locked || !models.length} onChange={(event) => setConAgentId(event.target.value)}>
            <option value="">选择模型</option>
            {models.map((agent) => <option key={agent.id} value={agent.id}>{modelLabel(agent)}</option>)}
          </select>
        </label>

        <div className="debate-side-summary">
          <div><span>正方</span><strong>{proAgent ? modelLabel(proAgent) : '未选择'}</strong></div>
          <div><span>反方</span><strong>{conAgent ? modelLabel(conAgent) : '未选择'}</strong></div>
        </div>

        <div className="debate-setup-note">点击“下一位发言”后才会调用模型，不限制辩论总轮数。</div>
      </aside>

      <section className="debate-stage">
        <div className="debate-stage-header">
          <div><span className="eyebrow">LIVE TRANSCRIPT</span><h2>{displayTopic || '等待输入辩题'}</h2></div>
          <div className={`debate-status ${loading ? 'busy' : ended ? 'ended' : started ? 'ready' : ''}`}><span />{statusText}</div>
        </div>

        {notice && <div className="notice debate-notice" role="status">{notice}<button onClick={() => setNotice('')}>×</button></div>}

        <div className="debate-transcript" aria-live="polite">
          {!turns.length && <div className="debate-empty"><div className="debate-orbit">⚖</div><h3>让两个 AI 观点交锋</h3><p>先完成设置，正方会从开篇立论开始。</p></div>}
          {turns.map((turn, index) => <article className={`debate-turn ${turn.side} ${loading && loadingSide === turn.side && index === turns.length - 1 ? 'streaming' : ''}`} key={`${turn.side}-${index}`}>
            <div className="debate-turn-meta"><span className="debate-side-pill">{sideLabel(turn.side)}</span><strong>{standardAgentName(turn.model_id, turn.display_name)}</strong><span>第 {index + 1} 次发言</span></div>
            <div className="debate-turn-content">
              {turn.content ? <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{ a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" /> }}
              >{prepareMarkdown(turn.content)}</ReactMarkdown> : <span className="stream-placeholder">…</span>}
            </div>
          </article>)}
          {loading && <div className="debate-thinking"><span className="pulse-dot" />{sideLabel(loadingSide ?? nextSide)}正在思考…</div>}
        </div>

        <div className="debate-actions">
          {!started && <button className="debate-primary-button" disabled={!canStart} onClick={() => void startDebate()}>开始辩论 <span>↗</span></button>}
          {started && !ended && <>
            <button className="debate-primary-button" disabled={busy} onClick={nextTurn}>让{sideLabel(nextSide)}发言 <span>→</span></button>
            <button className="debate-secondary-button" disabled={busy} onClick={() => void endCurrentDebate()}>结束辩论</button>
          </>}
          {ended && <span className="debate-ended-label">本次辩论已结束</span>}
          {!!turns.length && <button className="debate-reset-button" disabled={busy} onClick={resetDebate}>重新开始</button>}
        </div>
      </section>
    </div>
  </main>
}
