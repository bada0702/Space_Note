import { useState } from 'react'
import type { Category, Note } from '../../types'
import { useNotesStore } from '../../store/notesStore'

interface Props {
  category: Category
  notes: Note[]
  onSelectNote: (id: string) => void
  activeNoteId?: string
  onCreateNote: (categoryId: string) => void
}

function NoteItem({ note, isActive, onSelect }: { note: Note; isActive: boolean; onSelect: () => void }) {
  const { deleteNote } = useNotesStore()
  const [hovered, setHovered] = useState(false)

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (confirm(`"${note.title}" 노트를 삭제할까요?`)) {
      deleteNote(note.id)
    }
  }

  return (
    <li
      style={{ position: 'relative' }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        role="button"
        tabIndex={0}
        className="w-full text-left truncate"
        style={{
          fontSize: '13px',
          color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
          borderLeft: isActive ? '2px solid var(--accent-line)' : '2px solid transparent',
          paddingLeft: isActive ? '14px' : '16px',
          paddingRight: hovered ? '28px' : '12px',
          paddingTop: '3px',
          paddingBottom: '3px',
          display: 'block',
        }}
        onClick={onSelect}
        onKeyDown={e => e.key === 'Enter' && onSelect()}
      >
        {note.title}
      </button>
      {hovered && (
        <button
          onClick={handleDelete}
          style={{
            position: 'absolute',
            right: '6px',
            top: '50%',
            transform: 'translateY(-50%)',
            fontSize: '10px',
            color: 'var(--text-primary)',
            padding: '0 3px',
            lineHeight: 1,
            opacity: 0.8,
          }}
          onMouseEnter={e => ((e.currentTarget as HTMLButtonElement).style.opacity = '1')}
          onMouseLeave={e => ((e.currentTarget as HTMLButtonElement).style.opacity = '0.8')}
        >
          ✕
        </button>
      )}
    </li>
  )
}

export function CategoryItem({ category, notes, onSelectNote, activeNoteId, onCreateNote }: Props) {
  const [open, setOpen] = useState(true)
  const { setTab, setStarMapFilter } = useNotesStore()

  const showInStarMap = (e: React.MouseEvent) => {
    e.stopPropagation()
    setStarMapFilter(category.id)
    setTab('starmap')
  }

  return (
    <div className="mb-1">
      <div
        role="button"
        tabIndex={0}
        className="w-full flex items-center gap-1.5 px-3 py-1"
        style={{ color: 'var(--text-secondary)', fontSize: '11px', letterSpacing: '0.06em', textTransform: 'uppercase', cursor: 'pointer' }}
        onClick={() => setOpen(o => !o)}
        onKeyDown={e => e.key === 'Enter' && setOpen(o => !o)}
      >
        <span style={{ color: category.color, fontSize: '8px' }}>●</span>
        <span>{category.name}</span>
        <button
          title="성도에서 이 은하 보기"
          onClick={showInStarMap}
          className="ml-auto"
          style={{ fontSize: '10px', color: category.color, padding: '0 2px', lineHeight: 1 }}
        >
          ✦
        </button>
        <span style={{ fontSize: '9px' }}>{open ? '▾' : '▸'}</span>
      </div>

      {open && (
        <ul>
          {notes.map(note => (
            <NoteItem
              key={note.id}
              note={note}
              isActive={activeNoteId === note.id}
              onSelect={() => onSelectNote(note.id)}
            />
          ))}
          {notes.length === 0 && (
            <li className="px-4 py-1" style={{ fontSize: '11px', color: 'var(--text-secondary)', opacity: 0.5 }}>
              항해일지 없음
            </li>
          )}
          <li>
            <button
              className="w-full text-left px-4 py-1"
              style={{ fontSize: '11px', color: 'var(--text-secondary)', opacity: 0.5 }}
              onClick={() => onCreateNote(category.id)}
            >
              + 새 노트
            </button>
          </li>
        </ul>
      )}
    </div>
  )
}
