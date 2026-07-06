import { useState } from 'react'
import type { AIChatMessage } from '../../types'
import { useNotesStore } from '../../store/notesStore'

export function ChatMessage({ msg }: { msg: AIChatMessage }) {
  const isUser = msg.role === 'user'
  const { notes, createNote, setTab } = useNotesStore()
  const [saved, setSaved] = useState(false)
  const canSave = !isUser && !!msg.content && !msg.isStreaming && !msg.error

  const handleSave = async () => {
    if (!canSave || saved) return
    const firstLine = msg.content.split('\n').find(l => l.trim())?.trim() ?? ''
    const title = firstLine.length > 30 ? firstLine.slice(0, 30) + '…' : firstLine || `새 노트 ${notes.length + 1}`
    await createNote(title, undefined, msg.content)
    setTab('edit')
    setSaved(true)
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: isUser ? 'flex-end' : 'flex-start',
      marginBottom: 10,
    }}>
      <div style={{
        maxWidth: '80%',
        padding: '8px 12px',
        borderRadius: isUser ? '12px 12px 3px 12px' : '12px 12px 12px 3px',
        background: isUser ? 'var(--accent-primary)' : 'var(--bg-input)',
        color: msg.error ? '#ff6b6b' : isUser ? 'var(--accent-primary-text)' : 'var(--text-primary)',
        fontSize: 13,
        lineHeight: 1.6,
        border: msg.error ? '1px solid #ff6b6b44' : '1px solid transparent',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
      }}>
        {msg.content
          ? msg.content
          : msg.isStreaming
            ? <TypingDots />
            : null
        }
      </div>
      {canSave && (
        <button
          onClick={handleSave}
          disabled={saved}
          style={{
            marginTop: 4, fontSize: 10, color: saved ? 'var(--accent-line)' : 'var(--text-secondary)',
            background: 'none', border: '1px solid var(--border)', borderRadius: 4,
            padding: '2px 8px', cursor: saved ? 'default' : 'pointer', opacity: saved ? 1 : 0.7,
          }}
        >
          {saved ? '✓ 노트로 저장됨' : '⤓ 노트로 저장'}
        </button>
      )}
    </div>
  )
}

function TypingDots() {
  return (
    <span style={{ display: 'inline-flex', gap: 3, alignItems: 'center', height: 16 }}>
      {[0, 1, 2].map(i => (
        <span
          key={i}
          style={{
            width: 5, height: 5, borderRadius: '50%',
            background: 'var(--text-secondary)',
            animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
          }}
        />
      ))}
    </span>
  )
}
