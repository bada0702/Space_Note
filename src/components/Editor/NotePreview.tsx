import { marked } from 'marked'
import { useMemo } from 'react'
import { useNotesStore } from '../../store/notesStore'

const PROSE_CSS = `
.sn-prose { word-break: keep-all; overflow-wrap: anywhere; line-height: 1.85; font-size: var(--fs-lg); color: var(--text-primary); }
.sn-prose > :first-child { margin-top: 0; }
.sn-prose h1, .sn-prose h2, .sn-prose h3 { font-family: var(--font-title); font-weight: 700; line-height: 1.35; }
.sn-prose h1 { font-size: 28px; margin: 40px 0 16px; }
.sn-prose h2 { font-size: 22px; margin: 36px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.sn-prose h3 { font-size: 18px; margin: 28px 0 10px; }
.sn-prose h4 { font-size: var(--fs-lg); font-weight: 700; margin: 24px 0 8px; }
.sn-prose p  { margin: 0 0 16px; }
.sn-prose ul { margin: 0 0 16px; padding-left: 24px; list-style: disc; }
.sn-prose ol { margin: 0 0 16px; padding-left: 24px; list-style: decimal; }
.sn-prose li { margin: 4px 0; }
.sn-prose li::marker { color: var(--text-tertiary); }
.sn-prose li input[type=checkbox] { margin-right: 6px; accent-color: var(--star); }
.sn-prose blockquote { border-left: 2px solid var(--star); margin: 0 0 16px; padding: 2px 18px; color: var(--text-secondary); }
.sn-prose code { background: var(--bg-input); padding: 1px 5px; border-radius: 4px; font-size: 0.87em; font-family: var(--font-mono); }
.sn-prose pre  { background: var(--bg-input); border: 1px solid var(--border); padding: 14px 16px; border-radius: 8px; margin: 0 0 16px; overflow-x: auto; line-height: 1.6; }
.sn-prose pre code { background: none; padding: 0; font-size: 13px; }
.sn-prose hr   { border: none; text-align: center; margin: 32px 0; }
.sn-prose hr::after { content: '✦  ✦  ✦'; color: var(--text-tertiary); font-size: 11px; letter-spacing: 0.3em; }
.sn-prose a    { color: var(--star); text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: 3px; }
.sn-prose strong { font-weight: 700; }
.sn-prose em   { font-style: italic; }
.sn-prose del  { text-decoration: line-through; color: var(--text-secondary); }
.sn-prose img  { max-width: 100%; border-radius: 6px; }
.sn-prose table { border-collapse: collapse; margin: 0 0 16px; width: 100%; font-size: var(--fs-md); }
.sn-prose th, .sn-prose td { border-bottom: 1px solid var(--border); padding: 8px 12px; text-align: left; }
.sn-prose th { font-weight: 600; color: var(--text-secondary); border-bottom-color: var(--text-tertiary); }
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
        style={{ padding: '40px clamp(20px, 6vw, 64px) 80px' }}
      >
        <div
          className="sn-prose"
          style={{ maxWidth: '68ch', margin: '0 auto' }}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </div>
    </>
  )
}
