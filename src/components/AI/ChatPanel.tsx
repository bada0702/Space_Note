import { useEffect, useRef, useState } from 'react'
import { useAIStore } from '../../store/aiStore'
import { useNotesStore } from '../../store/notesStore'
import { ChatMessage } from './ChatMessage'
import type { AIModel } from '../../types'

const MODEL_LABELS: Record<AIModel, string> = {
  'claude-sonnet-4-6':   'Claude Sonnet',
  'claude-haiku-4-5':    'Claude Haiku',
  'gemini-2.0-flash':    'Gemini Flash',
  'gpt-4o-mini':         'GPT-4o mini',
  'gpt-4o':              'GPT-4o',
}

export function ChatPanel() {
  const {
    messages, model, context, streaming,
    sendMessage, setModel, setContext, clearMessages, loadSettings,
  } = useAIStore()
  const { activeNote } = useNotesStore()
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => { loadSettings() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])
  useEffect(() => {
    setContext({ noteId: activeNote?.id })
  }, [activeNote?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSend = () => {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')
    sendMessage(text)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-app)' }}>
      {/* 헤더 */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px',
        borderBottom: '1px solid var(--border)', flexShrink: 0,
      }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', flex: 1 }}>
          ✦ AI 채팅
        </span>
        <select
          value={model}
          onChange={e => setModel(e.target.value as AIModel)}
          style={{
            fontSize: 11, background: 'var(--bg-input)', color: 'var(--text-secondary)',
            border: '1px solid var(--border)', borderRadius: 4, padding: '2px 6px', cursor: 'pointer',
          }}
        >
          {(Object.keys(MODEL_LABELS) as AIModel[]).map(m => (
            <option key={m} value={m}>{MODEL_LABELS[m]}</option>
          ))}
        </select>
        <button
          onClick={clearMessages}
          style={{
            fontSize: 10, color: 'var(--text-secondary)', padding: '2px 6px',
            borderRadius: 3, border: '1px solid var(--border)',
            background: 'none', cursor: 'pointer',
          }}
        >
          초기화
        </button>
      </div>

      {/* 컨텍스트 옵션 */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '6px 14px',
        borderBottom: '1px solid var(--border)', flexShrink: 0, flexWrap: 'wrap',
      }}>
        <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={context.useRag}
            onChange={e => setContext({ useRag: e.target.checked })}
          />
          노트 RAG
        </label>
        <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={context.useWiki}
            onChange={e => setContext({ useWiki: e.target.checked })}
          />
          인터넷 검색
        </label>
        {activeNote && (
          <span style={{
            fontSize: 10, color: 'var(--accent-line)',
            background: 'var(--bg-input)', padding: '1px 7px', borderRadius: 10,
          }}>
            {activeNote.title.length > 16 ? activeNote.title.slice(0, 16) + '…' : activeNote.title}
          </span>
        )}
      </div>

      {/* 메시지 목록 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px' }}>
        {messages.length === 0 && (
          <div style={{
            height: '100%', display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: 8,
            color: 'var(--text-secondary)', opacity: 0.45,
          }}>
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
              <circle cx="16" cy="16" r="14" stroke="currentColor" strokeWidth="1.5" />
              <path d="M10 14 Q16 8 22 14 Q16 20 10 14Z" fill="currentColor" opacity="0.4" />
              <circle cx="16" cy="16" r="2" fill="currentColor" />
            </svg>
            <span style={{ fontSize: 12 }}>무엇이든 물어보세요</span>
          </div>
        )}
        {messages.map(msg => <ChatMessage key={msg.id} msg={msg} />)}
        <div ref={bottomRef} />
      </div>

      {/* 입력창 */}
      <div style={{
        padding: '10px 14px', borderTop: '1px solid var(--border)',
        flexShrink: 0, display: 'flex', gap: 8,
      }}>
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
          }}
          placeholder="메시지 입력... (Enter 전송, Shift+Enter 줄바꿈)"
          rows={2}
          style={{
            flex: 1, padding: '7px 10px', borderRadius: 6, resize: 'none',
            background: 'var(--bg-input)', color: 'var(--text-primary)',
            border: '1px solid var(--border)', fontSize: 12, outline: 'none',
            lineHeight: 1.5, fontFamily: 'inherit',
          }}
        />
        <button
          onClick={handleSend}
          disabled={streaming || !input.trim()}
          style={{
            padding: '0 14px', borderRadius: 6,
            background: (streaming || !input.trim()) ? 'var(--bg-input)' : 'var(--accent-primary)',
            color: (streaming || !input.trim()) ? 'var(--text-secondary)' : 'var(--accent-primary-text)',
            border: '1px solid var(--border)',
            cursor: (streaming || !input.trim()) ? 'not-allowed' : 'pointer',
            fontSize: 12, fontWeight: 600, alignSelf: 'flex-end', height: 34,
          }}
        >
          {streaming ? '…' : '전송'}
        </button>
      </div>
    </div>
  )
}
