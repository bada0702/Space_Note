import type { AIChatMessage } from '../../types'

export function ChatMessage({ msg }: { msg: AIChatMessage }) {
  const isUser = msg.role === 'user'

  return (
    <div style={{
      display: 'flex',
      justifyContent: isUser ? 'flex-end' : 'flex-start',
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
