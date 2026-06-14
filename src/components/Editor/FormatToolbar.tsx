import type * as monaco from 'monaco-editor'
import { useNotesStore } from '../../store/notesStore'

interface Props {
  editorRef: React.MutableRefObject<monaco.editor.IStandaloneCodeEditor | null>
}

interface ToolBtn {
  label: string
  title: string
  action: (editor: monaco.editor.IStandaloneCodeEditor) => void
}

function applyLinePrefix(editor: monaco.editor.IStandaloneCodeEditor, prefix: string) {
  const model = editor.getModel()
  const selection = editor.getSelection()
  if (!model || !selection) return

  const lineNum = selection.startLineNumber
  const lineContent = model.getLineContent(lineNum)

  const headingRegex = /^(#{1,3} |- \[[ x]\] |> |- |1\. )/
  const stripped = lineContent.replace(headingRegex, '')
  const newContent = lineContent.startsWith(prefix) ? stripped : prefix + stripped

  editor.executeEdits('format', [{
    range: {
      startLineNumber: lineNum,
      startColumn: 1,
      endLineNumber: lineNum,
      endColumn: model.getLineLength(lineNum) + 1,
    },
    text: newContent,
  }])
  editor.focus()
}

function wrapSelection(
  editor: monaco.editor.IStandaloneCodeEditor,
  before: string,
  after: string,
) {
  const selection = editor.getSelection()
  if (!selection) return
  const model = editor.getModel()
  if (!model) return

  const selected = model.getValueInRange(selection)
  editor.executeEdits('format', [{
    range: selection,
    text: `${before}${selected}${after}`,
  }])
  editor.focus()
}

function insertCodeBlock(editor: monaco.editor.IStandaloneCodeEditor) {
  const selection = editor.getSelection()
  if (!selection) return
  const model = editor.getModel()
  if (!model) return

  const selected = model.getValueInRange(selection)
  const text = selected ? `\`\`\`\n${selected}\n\`\`\`` : '```\n\n```'
  editor.executeEdits('format', [{ range: selection, text }])
  editor.focus()
}

function insertLink(editor: monaco.editor.IStandaloneCodeEditor) {
  const selection = editor.getSelection()
  if (!selection) return
  const model = editor.getModel()
  if (!model) return

  const selected = model.getValueInRange(selection)
  const text = selected ? `[${selected}](url)` : '[링크 텍스트](url)'
  editor.executeEdits('format', [{ range: selection, text }])
  editor.focus()
}

function insertHRule(editor: monaco.editor.IStandaloneCodeEditor) {
  const selection = editor.getSelection()
  if (!selection) return
  const model = editor.getModel()
  if (!model) return

  const lineNum = selection.startLineNumber
  const col = model.getLineLength(lineNum) + 1
  editor.executeEdits('format', [{
    range: {
      startLineNumber: lineNum,
      startColumn: col,
      endLineNumber: lineNum,
      endColumn: col,
    },
    text: '\n\n---\n',
  }])
  editor.focus()
}

function applyAlignment(
  editor: monaco.editor.IStandaloneCodeEditor,
  align: 'left' | 'center' | 'right',
) {
  const selection = editor.getSelection()
  if (!selection) return
  const model = editor.getModel()
  if (!model) return

  const selected = model.getValueInRange(selection)
  const text = selected || model.getLineContent(selection.startLineNumber)

  const stripped = text
    .replace(/^<div align="(left|center|right)">\n?/, '')
    .replace(/\n?<\/div>$/, '')

  const wrapped = align === 'left'
    ? stripped
    : `<div align="${align}">\n${stripped}\n</div>`

  if (selected) {
    editor.executeEdits('format', [{ range: selection, text: wrapped }])
  } else {
    const lineNum = selection.startLineNumber
    editor.executeEdits('format', [{
      range: {
        startLineNumber: lineNum,
        startColumn: 1,
        endLineNumber: lineNum,
        endColumn: model.getLineLength(lineNum) + 1,
      },
      text: wrapped,
    }])
  }
  editor.focus()
}

const GROUPS: ToolBtn[][] = [
  [
    { label: 'H1', title: '제목 1', action: e => applyLinePrefix(e, '# ') },
    { label: 'H2', title: '제목 2', action: e => applyLinePrefix(e, '## ') },
    { label: 'H3', title: '제목 3', action: e => applyLinePrefix(e, '### ') },
  ],
  [
    { label: 'B',  title: '굵게',   action: e => wrapSelection(e, '**', '**') },
    { label: 'I',  title: '기울임', action: e => wrapSelection(e, '*', '*') },
    { label: 'S',  title: '취소선', action: e => wrapSelection(e, '~~', '~~') },
  ],
  [
    { label: '·',    title: '글머리 기호',  action: e => applyLinePrefix(e, '- ') },
    { label: '1.',   title: '번호 목록',    action: e => applyLinePrefix(e, '1. ') },
    { label: '[ ]',  title: '체크박스',     action: e => applyLinePrefix(e, '- [ ] ') },
  ],
  [
    { label: '`',    title: '인라인 코드',  action: e => wrapSelection(e, '`', '`') },
    { label: '```',  title: '코드 블록',    action: e => insertCodeBlock(e) },
    { label: '>',    title: '인용구',       action: e => applyLinePrefix(e, '> ') },
    { label: '---',  title: '수평선',       action: e => insertHRule(e) },
    { label: 'URL',  title: '링크 삽입',    action: e => insertLink(e) },
  ],
  [
    { label: '≡L', title: '왼쪽 정렬',    action: e => applyAlignment(e, 'left') },
    { label: '≡C', title: '가운데 정렬',  action: e => applyAlignment(e, 'center') },
    { label: '≡R', title: '오른쪽 정렬', action: e => applyAlignment(e, 'right') },
  ],
]

export function FormatToolbar({ editorRef }: Props) {
  const { activeNote } = useNotesStore()

  const handlePrint = () => {
    if (!activeNote || !editorRef.current) return
    const content = editorRef.current.getValue()
    const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${activeNote.title}</title>
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
  <h1>${activeNote.title}</h1>
  <pre style="white-space: pre-wrap; font-family: inherit; background: none; padding: 0;">${content.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
</body>
</html>`
    const w = window.open('', '_blank')
    if (!w) return
    w.document.write(html)
    w.document.close()
    w.focus()
    w.print()
  }

  const btn = (b: ToolBtn) => (
    <button
      key={b.label + b.title}
      title={b.title}
      onMouseDown={e => {
        e.preventDefault()
        if (editorRef.current) b.action(editorRef.current)
      }}
      style={{
        fontSize: '11px',
        fontWeight: 500,
        color: 'var(--text-secondary)',
        padding: '2px 6px',
        borderRadius: '3px',
        lineHeight: 1.4,
        minWidth: '24px',
        textAlign: 'center',
        whiteSpace: 'nowrap',
        background: 'transparent',
      }}
      onMouseEnter={e => {
        ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--text-primary)'
        ;(e.currentTarget as HTMLButtonElement).style.background = 'var(--border)'
      }}
      onMouseLeave={e => {
        ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)'
        ;(e.currentTarget as HTMLButtonElement).style.background = 'transparent'
      }}
    >
      {b.label}
    </button>
  )

  const sep = (key: string) => (
    <div
      key={key}
      style={{ width: '1px', height: '12px', background: 'var(--border)', margin: '0 4px', flexShrink: 0 }}
    />
  )

  const items: React.ReactNode[] = []
  GROUPS.forEach((group, i) => {
    group.forEach(b => items.push(btn(b)))
    if (i < GROUPS.length - 1) items.push(sep(`sep-${i}`))
  })

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        padding: '3px 12px',
        gap: '1px',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
      }}
    >
      {items}

      {/* 구분선 + 인쇄 버튼 */}
      <div style={{ flex: 1 }} />
      {sep('sep-print')}
      <button
        title="인쇄"
        onClick={handlePrint}
        style={{
          fontSize: '11px',
          fontWeight: 500,
          color: 'var(--text-secondary)',
          padding: '2px 8px',
          borderRadius: '3px',
          lineHeight: 1.4,
          whiteSpace: 'nowrap',
          background: 'transparent',
          border: '1px solid var(--border)',
        }}
        onMouseEnter={e => {
          ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--text-primary)'
          ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--text-secondary)'
        }}
        onMouseLeave={e => {
          ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)'
          ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border)'
        }}
      >
        인쇄
      </button>
    </div>
  )
}
