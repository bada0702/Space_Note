import { useEffect, useState } from 'react'
import { useAIStore } from '../../store/aiStore'

function formatDate(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' })
}

/** AI 채팅 왼쪽의 대화 기록 목록 */
export function ConversationList() {
  const {
    conversations, conversationId, streaming,
    loadConversations, openConversation, deleteConversation, clearMessages,
  } = useAIStore()
  const [hovered, setHovered] = useState<string | null>(null)
  // 브라우저 confirm()은 환경(웹뷰·대화상자 차단)에 따라 뜨지 않을 수 있어 2단계 버튼으로 확인
  const [confirming, setConfirming] = useState<string | null>(null)

  useEffect(() => { loadConversations() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleDelete = (id: string) => {
    if (confirming !== id) {
      setConfirming(id)
      return
    }
    setConfirming(null)
    deleteConversation(id).catch(e => {
      console.error('대화 삭제 실패:', e)
      window.alert(`대화 삭제 실패: ${e instanceof Error ? e.message : e}`)
    })
  }

  return (
    <div style={{
      width: 240, flexShrink: 0, display: 'flex', flexDirection: 'column',
      borderRight: '1px solid var(--border)', background: 'var(--bg-panel)',
    }}>
      <div style={{ padding: '14px 12px', borderBottom: '1px solid var(--border)' }}>
        <button
          onClick={clearMessages}
          disabled={streaming}
          style={{
            width: '100%', padding: '7px 10px', borderRadius: 6,
            border: '1px solid var(--border)', background: 'var(--bg-input)',
            color: 'var(--text-primary)', fontSize: 13, fontWeight: 600,
            cursor: streaming ? 'not-allowed' : 'pointer',
          }}
        >
          + 새 대화
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '6px 6px 12px' }}>
        {conversations.length === 0 && (
          <div style={{ padding: '16px 8px', fontSize: 12, color: 'var(--text-tertiary)', textAlign: 'center' }}>
            저장된 대화가 없습니다
          </div>
        )}
        {conversations.map(c => {
          const active = c.id === conversationId
          return (
            <div
              key={c.id}
              onClick={() => openConversation(c.id).catch(e => console.error('대화 열기 실패:', e))}
              onMouseEnter={() => setHovered(c.id)}
              onMouseLeave={() => { setHovered(null); setConfirming(null) }}
              title={c.title}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '7px 8px', borderRadius: 5, marginBottom: 2,
                cursor: streaming ? 'not-allowed' : 'pointer',
                background: active ? 'var(--bg-input)' : hovered === c.id ? 'var(--bg-input)' : 'transparent',
                borderLeft: active ? '2px solid var(--accent-primary)' : '2px solid transparent',
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 13, color: 'var(--text-primary)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {c.title}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 1 }}>
                  {formatDate(c.updated_at)}
                </div>
              </div>
              {confirming === c.id ? (
                <button
                  onClick={e => { e.stopPropagation(); handleDelete(c.id) }}
                  aria-label="삭제 확인"
                  style={{
                    border: '1px solid var(--danger)', background: 'none', color: 'var(--danger)',
                    cursor: 'pointer', fontSize: 11, padding: '2px 6px', borderRadius: 4, flexShrink: 0,
                  }}
                >
                  삭제
                </button>
              ) : (
                <button
                  onClick={e => { e.stopPropagation(); handleDelete(c.id) }}
                  aria-label="대화 삭제"
                  style={{
                    border: 'none', background: 'none', color: 'var(--text-secondary)',
                    opacity: hovered === c.id || active ? 1 : 0.35,
                    cursor: 'pointer', fontSize: 16, padding: '0 4px', lineHeight: 1, flexShrink: 0,
                  }}
                >
                  ×
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
