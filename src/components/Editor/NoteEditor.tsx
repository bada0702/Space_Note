import Editor from '@monaco-editor/react'
import type * as monaco from 'monaco-editor'
import { useNotesStore } from '../../store/notesStore'
import { useTheme } from '../Layout/ThemeProvider'
import { useRef, useCallback } from 'react'
import { FormatToolbar, uploadAndInsert } from './FormatToolbar'

export function NoteEditor() {
  const { activeNote, saveNote } = useNotesStore()
  const { theme } = useTheme()
  const saveTimer = useRef<ReturnType<typeof setTimeout>>()
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null)

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
