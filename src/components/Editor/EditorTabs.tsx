import { useState, useEffect, useRef } from 'react'
import { useNotesStore } from '../../store/notesStore'
import { formatDateTime } from '../../utils/dateFormat'
import type { EditorTab } from '../../types'

export function EditorTabs() {
  const { activeNote, activeTab, setTab, setStarMapFilter, deleteNote, renameNote, toggleFavorite } = useNotesStore()
  const [titleValue, setTitleValue] = useState('')
  const titleRef = useRef<HTMLInputElement>(null)

  // activeNote가 바뀌면 제목 동기화
  useEffect(() => {
    if (activeNote) {
      setTitleValue(activeNote.title)
      // 새 노트면 제목 필드 자동 포커스
      if (/^새 노트/.test(activeNote.title)) {
        setTimeout(() => titleRef.current?.select(), 50)
      }
    }
  }, [activeNote?.id])

  if (!activeNote) return null

  const handleTitleBlur = () => {
    if (activeNote && titleValue.trim() && titleValue !== activeNote.title) {
      renameNote(activeNote.id, titleValue)
    }
  }

  const handleTitleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.currentTarget.blur()
    }
    if (e.key === 'Escape') {
      setTitleValue(activeNote?.title ?? '')
      e.currentTarget.blur()
    }
  }

  const handleDelete = () => {
    if (confirm(`"${activeNote.title}" 노트를 삭제할까요?`)) {
      deleteNote(activeNote.id)
    }
  }

  const handlePrint = () => {
    if (!activeNote) return
    const content = activeNote.content || ""
    const escapeHtml = (s: string) => s.replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const title = escapeHtml(activeNote.title)
    const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${title}</title>
  <style>
    body { font-family: 'Pretendard', 'Inter', sans-serif; font-size: 14px; line-height: 1.8; max-width: 800px; margin: 40px auto; color: #0a0a0a; }
    h1 { font-size: 24px; font-weight: 700; margin: 24px 0 12px; }
    h2 { font-size: 20px; font-weight: 600; margin: 20px 0 10px; }
    h3 { font-size: 16px; font-weight: 600; margin: 16px 0 8px; }
    pre { background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; }
    code { background: #f0f0f0; padding: 1px 4px; border-radius: 3px; font-size: 13px; }
    blockquote { border-left: 3px solid #ccc; margin: 0; padding-left: 16px; color: #555; }
    hr { border: none; border-top: 1px solid #e0e0e0; margin: 24px 0; }
    @media print { body { margin: 20px; } }
  </style>
</head>
<body>
  <h1>${title}</h1>
  <pre style="white-space: pre-wrap; font-family: inherit; background: none; padding: 0;">${escapeHtml(content)}</pre>
</body>
</html>`
    const w = window.open('', '_blank')
    if (!w) return
    w.document.write(html)
    w.document.close()
    w.focus()
    w.print()
  }

  return (
    <div className="glass glass-bar flex items-center px-4 gap-3">
      {/* 제목 입력 + 기항지 토글 + 날짜 시간 */}
      <div className="flex flex-col py-3 min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <input
            ref={titleRef}
            value={titleValue}
            onChange={e => setTitleValue(e.target.value)}
            onBlur={handleTitleBlur}
            onKeyDown={handleTitleKeyDown}
            placeholder="제목 없음"
            style={{
              fontSize: '14px',
              fontWeight: 600,
              color: 'var(--text-primary)',
              background: 'transparent',
              border: 'none',
              outline: 'none',
              padding: 0,
              margin: 0,
              flex: 1,
              minWidth: 0,
            }}
          />
          <button
            title={activeNote.is_favorite ? '기항지 해제' : '기항지로 지정'}
            onClick={() => toggleFavorite(activeNote.id)}
            style={{
              fontSize: '14px',
              color: activeNote.is_favorite ? '#E8B23A' : 'var(--text-secondary)',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              opacity: activeNote.is_favorite ? 1 : 0.55,
              padding: '0 4px',
              lineHeight: 1,
            }}
          >
            {activeNote.is_favorite ? '★' : '☆'}
          </button>
        </div>
        <div className="flex items-center gap-3" style={{ fontSize: '10px', color: 'var(--text-secondary)', opacity: 0.8, marginTop: '2px' }}>
          <span>생성: {formatDateTime(activeNote.created_at)}</span>
          <span>수정: {formatDateTime(activeNote.modified_at)}</span>
        </div>
      </div>

      {/* 탭 버튼 */}
      <div className="flex items-center gap-0 flex-shrink-0" style={{ flexShrink: 0 }}>
        {/* 1. 편집 */}
        <button
          onClick={() => setTab('edit')}
          className="px-3 py-2.5"
          style={{
            fontSize: '12px',
            color: activeTab === 'edit' ? 'var(--text-primary)' : 'var(--text-secondary)',
            borderBottom: activeTab === 'edit' ? '2px solid var(--accent-line)' : '2px solid transparent',
            whiteSpace: 'nowrap',
          }}
        >
          편집
        </button>

        {/* 2. 미리보기 */}
        <button
          onClick={() => setTab('preview')}
          className="px-3 py-2.5"
          style={{
            fontSize: '12px',
            color: activeTab === 'preview' ? 'var(--text-primary)' : 'var(--text-secondary)',
            borderBottom: activeTab === 'preview' ? '2px solid var(--accent-line)' : '2px solid transparent',
            whiteSpace: 'nowrap',
          }}
        >
          미리보기
        </button>

        {/* 3. 인쇄 */}
        <button
          onClick={handlePrint}
          className="px-3 py-2.5"
          style={{
            fontSize: '12px',
            color: 'var(--text-secondary)',
            borderBottom: '2px solid transparent',
            whiteSpace: 'nowrap',
          }}
          onMouseEnter={e => {
            ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--text-primary)'
          }}
          onMouseLeave={e => {
            ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)'
          }}
        >
          인쇄
        </button>

        {/* 4. 성도 */}
        <button
          onClick={() => {
            setStarMapFilter(activeNote?.category_id ? { type: 'category', value: activeNote.category_id } : null)
            setTab('starmap')
          }}
          className="px-3 py-2.5"
          style={{
            fontSize: '12px',
            color: activeTab === 'starmap' ? 'var(--text-primary)' : 'var(--text-secondary)',
            borderBottom: activeTab === 'starmap' ? '2px solid var(--accent-line)' : '2px solid transparent',
            whiteSpace: 'nowrap',
          }}
        >
          성도
        </button>

        <div style={{ width: '1px', height: '14px', background: 'var(--border)', margin: '0 8px' }} />
        
        {/* 5. 삭제 */}
        <button
          onClick={handleDelete}
          style={{
            fontSize: '11px',
            color: 'var(--text-secondary)',
            padding: '2px 8px',
            borderRadius: '3px',
            border: '1px solid var(--border)',
            whiteSpace: 'nowrap',
          }}
          onMouseEnter={e => {
            ;(e.currentTarget as HTMLButtonElement).style.color = '#C92A2A'
            ;(e.currentTarget as HTMLButtonElement).style.borderColor = '#C92A2A'
          }}
          onMouseLeave={e => {
            ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)'
            ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border)'
          }}
        >
          삭제
        </button>
      </div>
    </div>
  )
}
