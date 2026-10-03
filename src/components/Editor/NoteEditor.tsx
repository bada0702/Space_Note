import Editor, { type BeforeMount } from '@monaco-editor/react'
import type * as monaco from 'monaco-editor'
import { useNotesStore } from '../../store/notesStore'
import { useTheme } from '../Layout/ThemeProvider'
import { useRef, useCallback } from 'react'
import { FormatToolbar, uploadAndInsert } from './FormatToolbar'

// 앱 토큰과 맞춘 Monaco 테마 (밤하늘 / 성도 인쇄본)
const defineThemes: BeforeMount = monacoApi => {
  monacoApi.editor.defineTheme('sn-night', {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'keyword', foreground: 'E9C46A', fontStyle: 'bold' },
      { token: 'strong', foreground: 'E6EAF2', fontStyle: 'bold' },
      { token: 'emphasis', fontStyle: 'italic' },
      { token: 'string.link', foreground: 'E9C46A' },
      { token: 'variable', foreground: '9AA6BD' },
      { token: 'comment', foreground: '75829B' },
    ],
    colors: {
      'editor.background': '#0D1524',
      'editor.foreground': '#E6EAF2',
      'editorLineNumber.foreground': '#3A4963',
      'editorLineNumber.activeForeground': '#9AA6BD',
      'editorCursor.foreground': '#E9C46A',
      'editor.selectionBackground': '#E9C46A33',
      'editor.inactiveSelectionBackground': '#E9C46A1A',
      'editorWidget.background': '#121C2E',
      'editorWidget.border': '#24324A',
    },
  })
  monacoApi.editor.defineTheme('sn-chart', {
    base: 'vs',
    inherit: true,
    rules: [
      { token: 'keyword', foreground: '8A5A0B', fontStyle: 'bold' },
      { token: 'strong', foreground: '16233A', fontStyle: 'bold' },
      { token: 'emphasis', fontStyle: 'italic' },
      { token: 'string.link', foreground: '8A5A0B' },
      { token: 'variable', foreground: '55627A' },
      { token: 'comment', foreground: '7A869C' },
    ],
    colors: {
      'editor.background': '#EDF0F5',
      'editor.foreground': '#16233A',
      'editorLineNumber.foreground': '#AEB8C8',
      'editorLineNumber.activeForeground': '#55627A',
      'editorCursor.foreground': '#8A5A0B',
      'editor.selectionBackground': '#8A5A0B26',
      'editor.inactiveSelectionBackground': '#8A5A0B14',
    },
  })
}

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
        <svg width="64" height="64" viewBox="0 0 48 48" fill="none" style={{ opacity: 0.3 }} aria-hidden="true">
          <ellipse cx="24" cy="24" rx="22" ry="10" stroke="currentColor" strokeWidth="1.5" />
          <circle cx="24" cy="24" r="3" fill="var(--star)" />
          <circle cx="6" cy="20" r="1" fill="currentColor" opacity="0.4" />
          <circle cx="42" cy="28" r="0.8" fill="currentColor" opacity="0.3" />
          <circle cx="36" cy="16" r="0.5" fill="currentColor" opacity="0.5" />
        </svg>
        <p style={{ fontFamily: 'var(--font-title)', fontSize: '18px', color: 'var(--text-primary)' }}>열린 노트가 없습니다</p>
        <p style={{ fontSize: 'var(--fs-sm)' }}>왼쪽 항해일지에서 노트를 고르거나, 은하의 ‘+ 새 노트’로 시작하세요.</p>
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
          theme={theme === 'dark' ? 'sn-night' : 'sn-chart'}
          beforeMount={defineThemes}
          onChange={handleChange}
          onMount={editor => { editorRef.current = editor }}
          options={{
            fontSize: 15,
            lineHeight: 1.7,
            wordWrap: 'on',
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            padding: { top: 20, bottom: 24 },
            fontFamily: '"JetBrains Mono", "Pretendard Variable", "Pretendard", monospace',
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
