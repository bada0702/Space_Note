import { useState } from 'react'
import type { Category, Note } from '../../types'
import { useNotesStore } from '../../store/notesStore'
import { useCategoriesStore } from '../../store/categoriesStore'

export const NOTE_DRAG_MIME = 'application/x-spacenote-note-id'

interface Props {
  category: Category
  notes: Note[]
  onSelectNote: (id: string) => void
  activeNoteId?: string
  onCreateNote: (categoryId: string) => void
  onDropNote: (noteId: string) => void
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
        draggable
        onDragStart={e => e.dataTransfer.setData(NOTE_DRAG_MIME, note.id)}
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
          cursor: 'grab',
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

export function CategoryItem({ category, notes, onSelectNote, activeNoteId, onCreateNote, onDropNote }: Props) {
  const [open, setOpen] = useState(true)
  const [hovered, setHovered] = useState(false)
  const [editing, setEditing] = useState(false)
  const [nameValue, setNameValue] = useState(category.name)
  const [dragOver, setDragOver] = useState(false)
  const { setTab, setStarMapFilter } = useNotesStore()
  const { updateCategory } = useCategoriesStore()

  const handleDragOver = (e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes(NOTE_DRAG_MIME)) return
    e.preventDefault()
    setDragOver(true)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const noteId = e.dataTransfer.getData(NOTE_DRAG_MIME)
    if (noteId) onDropNote(noteId)
  }

  const showInStarMap = (e: React.MouseEvent) => {
    e.stopPropagation()
    setStarMapFilter({ type: 'category', value: category.id })
    setTab('starmap')
  }

  const startEdit = (e: React.MouseEvent) => {
    e.stopPropagation()
    setNameValue(category.name)
    setEditing(true)
  }

  const saveName = async () => {
    const name = nameValue.trim()
    setEditing(false)
    if (!name || name === category.name) return
    try {
      await updateCategory(category.id, { name })
    } catch (e) {
      console.error('category rename failed:', e)
    }
  }

  return (
    <div className="mb-1">
      <div
        role="button"
        tabIndex={0}
        className="w-full flex items-center gap-1.5 px-3 py-1"
        style={{
          color: 'var(--text-secondary)', fontSize: '11px', letterSpacing: '0.06em', textTransform: 'uppercase', cursor: 'pointer',
          background: dragOver ? 'var(--bg-input)' : undefined,
          outline: dragOver ? '1px dashed var(--accent-line)' : undefined,
        }}
        onClick={() => !editing && setOpen(o => !o)}
        onKeyDown={e => e.key === 'Enter' && !editing && setOpen(o => !o)}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onDragOver={handleDragOver}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <span style={{ color: category.color, fontSize: '8px' }}>●</span>
        {editing ? (
          <input
            autoFocus
            value={nameValue}
            onChange={e => setNameValue(e.target.value)}
            onClick={e => e.stopPropagation()}
            onBlur={saveName}
            onKeyDown={e => {
              e.stopPropagation()
              if (e.key === 'Enter') saveName()
              if (e.key === 'Escape') setEditing(false)
            }}
            style={{
              flex: 1, minWidth: 0, fontSize: '11px',
              letterSpacing: '0.06em', textTransform: 'uppercase',
              background: 'var(--bg-input)', color: 'var(--text-primary)',
              border: '1px solid var(--border)', borderRadius: '3px',
              padding: '0 4px', outline: 'none',
            }}
          />
        ) : (
          <span>{category.name}</span>
        )}
        {!editing && hovered && (
          <button
            title="이름 수정"
            onClick={startEdit}
            style={{ fontSize: '10px', color: 'var(--text-secondary)', padding: '0 2px', lineHeight: 1 }}
          >
            ✎
          </button>
        )}
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
