import { marked } from 'marked'
import { useMemo } from 'react'
import { useNotesStore } from '../../store/notesStore'

const PROSE_CSS = `
.sn-prose { word-break: break-word; overflow-wrap: anywhere; line-height: 1.8; font-size: 15px; }
.sn-prose h1 { font-size: 24px; font-weight: 700; margin: 28px 0 12px; line-height: 1.3; }
.sn-prose h2 { font-size: 20px; font-weight: 600; margin: 24px 0 10px; line-height: 1.4; }
.sn-prose h3 { font-size: 17px; font-weight: 600; margin: 20px 0 8px; line-height: 1.4; }
.sn-prose p  { margin: 0 0 14px; }
.sn-prose ul { margin: 0 0 14px; padding-left: 24px; list-style: disc; }
.sn-prose ol { margin: 0 0 14px; padding-left: 24px; list-style: decimal; }
.sn-prose li { margin: 4px 0; }
.sn-prose li input[type=checkbox] { margin-right: 6px; }
.sn-prose blockquote { border-left: 3px solid var(--border); margin: 0 0 14px; padding: 4px 16px; color: var(--text-secondary); }
.sn-prose code { background: var(--bg-input); padding: 1px 5px; border-radius: 3px; font-size: 13px; font-family: "JetBrains Mono", monospace; }
.sn-prose pre  { background: var(--bg-input); padding: 14px 16px; border-radius: 3px; margin: 0 0 14px; overflow-x: auto; }
.sn-prose pre code { background: none; padding: 0; font-size: 13px; }
.sn-prose hr   { border: none; border-top: 1px solid var(--border); margin: 24px 0; }
.sn-prose a    { color: var(--text-primary); text-decoration: underline; text-underline-offset: 3px; }
.sn-prose strong { font-weight: 700; }
.sn-prose em   { font-style: italic; }
.sn-prose del  { text-decoration: line-through; color: var(--text-secondary); }
.sn-prose table { border-collapse: collapse; margin: 0 0 14px; width: 100%; }
.sn-prose th, .sn-prose td { border: 1px solid var(--border); padding: 6px 12px; }
.sn-prose th { background: var(--bg-input); font-weight: 600; }
`

export function NotePreview() {
  const { activeNote } = useNotesStore()

  const html = useMemo(() => {
    if (!activeNote?.content) return ''
    return marked.parse(activeNote.content, { gfm: true, breaks: true }) as string
  }, [activeNote?.content])

  if (!activeNote) return null

  return (
    <>
      <style>{PROSE_CSS}</style>
      <div
        className="h-full overflow-y-auto"
        style={{ padding: '32px 48px', color: 'var(--text-primary)' }}
      >
        <div
          className="sn-prose"
          style={{ maxWidth: '720px', margin: '0 auto' }}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </div>
    </>
  )
}
