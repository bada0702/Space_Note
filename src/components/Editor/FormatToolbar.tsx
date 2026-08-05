import type * as monaco from 'monaco-editor'
import { attachmentMarkdown, uploadAttachment } from '../../api/attachmentsApi'

/** 커서 위치(또는 선택 영역)에 텍스트 삽입 */
export function insertAtCursor(editor: monaco.editor.IStandaloneCodeEditor, text: string) {
  const selection = editor.getSelection()
  if (!selection) return
  editor.executeEdits('attach', [{ range: selection, text }])
  editor.focus()
}

/** 파일들을 업로드하고 각각 마크다운 링크로 삽입 */
export async function uploadAndInsert(
  editor: monaco.editor.IStandaloneCodeEditor,
  files: Iterable<File>,
) {
  for (const file of files) {
    try {
      const uploaded = await uploadAttachment(file)
      insertAtCursor(editor, `${attachmentMarkdown(uploaded)}\n`)
    } catch (e) {
      console.error('attachment upload failed:', e)
      insertAtCursor(editor, `<!-- 업로드 실패: ${file.name} -->\n`)
    }
  }
}

function pickAndUpload(editor: monaco.editor.IStandaloneCodeEditor) {
  const input = document.createElement('input')
  input.type = 'file'
  input.multiple = true
  input.onchange = () => {
    if (input.files?.length) uploadAndInsert(editor, input.files)
  }
  input.click()
}

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
    { label: '📎',   title: '파일 첨부',    action: e => pickAndUpload(e) },
  ],
  [
    { label: '≡L', title: '왼쪽 정렬',    action: e => applyAlignment(e, 'left') },
    { label: '≡C', title: '가운데 정렬',  action: e => applyAlignment(e, 'center') },
    { label: '≡R', title: '오른쪽 정렬', action: e => applyAlignment(e, 'right') },
  ],
]

export function FormatToolbar({ editorRef }: Props) {

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
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
      }}
    >
      {/* 왼쪽 여백 — 서식 버튼을 가운데로 밀기 */}
      <div style={{ flex: 1 }} />

      <div style={{ display: 'flex', alignItems: 'center', gap: '1px' }}>
        {items}
      </div>

      {/* 오른쪽 여백 — 서식 버튼을 가운데로 밀기 */}
      <div style={{ flex: 1 }} />
    </div>
  )
}
