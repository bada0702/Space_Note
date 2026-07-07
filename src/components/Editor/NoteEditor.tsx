import Editor from '@monaco-editor/react'
import type * as monaco from 'monaco-editor'
import { useNotesStore } from '../../store/notesStore'
import { useTheme } from '../Layout/ThemeProvider'
import { useRef, useCallback, useState, useEffect } from 'react'
import { FormatToolbar, uploadAndInsert } from './FormatToolbar'
import { formatDateTime } from '../../utils/dateFormat'

export function NoteEditor() {
  const { activeNote, saveNote, renameNote, toggleFavorite } = useNotesStore()
  const { theme } = useTheme()
  const saveTimer = useRef<ReturnType<typeof setTimeout>>()
  const [titleValue, setTitleValue] = useState('')
  const titleRef = useRef<HTMLInputElement>(null)
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)

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

  const handleChange = useCallback((value: string | undefined) => {
    if (!activeNote || value === undefined) return
    clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      saveNote(activeNote.id, value)
    }, 1000)
  }, [activeNote, saveNote])

  if (!activeNote) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3" style={{ color: 'var(--text-secondary)' }}>
        <svg width="64" height="64" viewBox="0 0 48 48" fill="none" style={{ opacity: 0.08 }}>
          <ellipse cx="24" cy="24" rx="22" ry="10" stroke="currentColor" strokeWidth="1.5" />
          <circle cx="24" cy="24" r="3" fill="currentColor" />
          <circle cx="6" cy="20" r="1" fill="currentColor" opacity="0.4" />
          <circle cx="42" cy="28" r="0.8" fill="currentColor" opacity="0.3" />
          <circle cx="36" cy="16" r="0.5" fill="currentColor" opacity="0.5" />
        </svg>
        <p style={{ fontSize: '13px' }}>노트를 선택하거나 새로 만드세요</p>
        <p style={{ fontSize: '11px', opacity: 0.5 }}>← 왼쪽에서 은하를 만들고 항해일지를 추가하세요</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* 제목 입력 + 기항지 토글 */}
      <div style={{
        display: 'flex', alignItems: 'center', flexShrink: 0,
      }}>
        <input
          ref={titleRef}
          value={titleValue}
          onChange={e => setTitleValue(e.target.value)}
          onBlur={handleTitleBlur}
          onKeyDown={handleTitleKeyDown}
          placeholder="제목 없음"
          style={{
            flex: 1,
            minWidth: 0,
            padding: '14px 8px 10px 48px',
            fontSize: '16px',
            fontWeight: 600,
            color: 'var(--text-primary)',
            background: 'transparent',
            border: 'none',
            outline: 'none',
          }}
        />
        <button
          title={activeNote.is_favorite ? '기항지 해제' : '기항지로 지정'}
          onClick={() => toggleFavorite(activeNote.id)}
          style={{
            fontSize: '15px', padding: '10px 16px 6px', lineHeight: 1,
            color: activeNote.is_favorite ? '#E8B23A' : 'var(--text-secondary)',
            background: 'transparent', border: 'none', cursor: 'pointer',
            opacity: activeNote.is_favorite ? 1 : 0.55,
          }}
        >
          {activeNote.is_favorite ? '★' : '☆'}
        </button>
      </div>

      {/* 노트 메타데이터: 생성일·수정일 */}
      <div style={{
        display: 'flex', gap: 16, flexShrink: 0,
        padding: '4px 16px 6px 48px',
        fontSize: '10.5px', color: 'var(--text-secondary)', opacity: 0.75,
        borderBottom: '1px solid var(--border)',
        whiteSpace: 'nowrap', overflow: 'hidden',
      }}>
        <span>최초 생성일: {formatDateTime(activeNote.created_at)}</span>
        <span>최근 수정일: {formatDateTime(activeNote.modified_at)}</span>
      </div>

      {/* 서식 툴바 */}
      <FormatToolbar editorRef={editorRef} />
      {/* 본문 에디터 (파일 드래그앤드롭/붙여넣기로 첨부 업로드) */}
      <div
        className="flex-1 overflow-hidden"
        onDragOver={e => {
          if (e.dataTransfer.types.includes('Files')) e.preventDefault()
        }}
        onDrop={e => {
          if (!e.dataTransfer.files.length || !editorRef.current) return
          e.preventDefault()
          uploadAndInsert(editorRef.current, e.dataTransfer.files)
        }}
        onPaste={e => {
          if (!e.clipboardData.files.length || !editorRef.current) return
          e.preventDefault()
          e.stopPropagation()
          uploadAndInsert(editorRef.current, e.clipboardData.files)
        }}
      >
        <Editor
          height="100%"
          defaultLanguage="markdown"
          value={activeNote.content}
          theme={theme === 'dark' ? 'vs-dark' : 'light'}
          onChange={handleChange}
          onMount={editor => { editorRef.current = editor }}
          options={{
            fontSize: 15,
            lineHeight: 1.7,
            wordWrap: 'on',
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            padding: { top: 20, bottom: 24 },
            fontFamily: '"JetBrains Mono", "Pretendard", monospace',
            renderLineHighlight: 'none',
            overviewRulerLanes: 0,
            folding: false,
            lineNumbers: 'on',
            glyphMargin: false,
          }}
        />
      </div>
    </div>
  )
}
