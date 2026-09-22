import { useState } from 'react'

export function Composer({ onSend }: { onSend: (content: string) => Promise<void> }) {
  const [value, setValue] = useState('')
  const [sending, setSending] = useState(false)
  const submit = async () => {
    const content = value.trim()
    if (!content || sending) return
    setSending(true)
    try { await onSend(content); setValue('') } finally { setSending(false) }
  }
  return <div className="composer-wrap"><div className="composer"><textarea value={value} onChange={(event) => setValue(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit() } }} placeholder="输入消息，使用 @ 指定 AI…" rows={2} /><div className="composer-actions"><span className="composer-hint">Enter 发送 · Shift + Enter 换行</span><button className="send-button" onClick={() => void submit()} disabled={sending || !value.trim()}>{sending ? '发送中…' : '发送'} <span>↗</span></button></div></div></div>
}
