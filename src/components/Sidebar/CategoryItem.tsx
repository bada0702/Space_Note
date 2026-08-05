import { useState } from 'react'
import type { Category, Note } from '../../types'
import { useNotesStore } from '../../store/notesStore'
import { useCategoriesStore } from '../../store/categoriesStore'

export const NOTE_DRAG_MIME = 'application/x-spacenote-note-id'

const CATEGORY_COLOR_PRESETS = [
  '#F0635A', '#F2994A', '#E8B23A', '#4C9A6A',
  '#3AA0A0', '#4C6EF5', '#9775FA', '#E64980',
]

interface Props {
  category: Category
  notes: Note[]
  onSelectNote: (id: string) => void
  onDoubleClickNote: (id: string) => void
  activeNoteId?: string
  onCreateNote: (categoryId: string) => void
  onDropNote: (noteId: string) => void
}

function NoteItem({
  note,
  isActive,
  onSelect,
  onDoubleClick
}: {
  note: Note
  isActive: boolean
  onSelect: () => void
  onDoubleClick: () => void
}) {
  const { deleteNote, toggleFavorite, archiveNote } = useNotesStore()
  const [hovered, setHovered] = useState(false)
  const [lastClick, setLastClick] = useState(0)

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (confirm(`"${note.title}" 노트를 삭제할까요?`)) {
      deleteNote(note.id)
    }
  }

  const handleClick = () => {
    const now = Date.now()
    if (now - lastClick < 300) {
      onDoubleClick()
    } else {
      onSelect()
    }
    setLastClick(now)
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
          paddingRight: hovered ? '62px' : note.is_favorite ? '24px' : '12px',
          paddingTop: '3px',
          paddingBottom: '3px',
          display: 'block',
          cursor: 'grab',
        }}
        onClick={handleClick}
        onKeyDown={e => e.key === 'Enter' && onSelect()}
      >
        {note.title}
      </button>
      {(hovered || note.is_favorite) && (
        <button
          title={note.is_favorite ? '기항지 해제' : '기항지로 지정'}
          onClick={e => { e.stopPropagation(); toggleFavorite(note.id) }}
          style={{
            position: 'absolute',
            right: hovered ? '38px' : '6px',
            top: '50%',
            transform: 'translateY(-50%)',
            fontSize: '10px',
            color: note.is_favorite ? '#E8B23A' : 'var(--text-secondary)',
            padding: '0 3px',
            lineHeight: 1,
            opacity: note.is_favorite ? 1 : 0.7,
          }}
        >
          {note.is_favorite ? '★' : '☆'}
        </button>
      )}
      {hovered && (
        <button
          title="블랙홀로 보내기 (보관)"
          onClick={e => { e.stopPropagation(); archiveNote(note.id) }}
          style={{
            position: 'absolute',
            right: '22px',
            top: '50%',
            transform: 'translateY(-50%)',
            fontSize: '10px',
            color: 'var(--text-secondary)',
            padding: '0 3px',
            lineHeight: 1,
            opacity: 0.7,
          }}
          onMouseEnter={e => ((e.currentTarget as HTMLButtonElement).style.opacity = '1')}
          onMouseLeave={e => ((e.currentTarget as HTMLButtonElement).style.opacity = '0.7')}
        >
          ◐
        </button>
      )}
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

export function CategoryItem({ category, notes, onSelectNote, onDoubleClickNote, activeNoteId, onCreateNote, onDropNote }: Props) {
  const [open, setOpen] = useState(true)
  const [hovered, setHovered] = useState(false)
  const [editing, setEditing] = useState(false)
  const [nameValue, setNameValue] = useState(category.name)
  const [dragOver, setDragOver] = useState(false)
  const [colorPickerOpen, setColorPickerOpen] = useState(false)
  const { setTab, setStarMapFilter } = useNotesStore()
  const { updateCategory, deleteCategory } = useCategoriesStore()

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (confirm(`"${category.name}" 은하(카테고리)를 삭제할까요?\n은하에 속한 노트들은 보존됩니다.`)) {
      try {
        await deleteCategory(category.id)
      } catch (err) {
        console.error('category delete failed:', err)
      }
    }
  }

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

  const pickColor = async (color: string) => {
    setColorPickerOpen(false)
    if (color === category.color) return
    try {
      await updateCategory(category.id, { color })
    } catch (e) {
      console.error('category color change failed:', e)
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
        <span style={{ position: 'relative', display: 'inline-flex' }}>
          <button
            type="button"
            title="카테고리 색상 변경"
            onClick={e => { e.stopPropagation(); setColorPickerOpen(o => !o) }}
            style={{ color: category.color ?? 'var(--text-secondary)', fontSize: '8px', lineHeight: 1, cursor: 'pointer' }}
          >
            ●
          </button>
          {colorPickerOpen && (
            <>
              <div
                style={{ position: 'fixed', inset: 0, zIndex: 10 }}
                onClick={e => { e.stopPropagation(); setColorPickerOpen(false) }}
              />
              <div
                onClick={e => e.stopPropagation()}
                style={{
                  position: 'absolute', top: '14px', left: 0, zIndex: 11,
                  display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '4px',
                  padding: '6px', borderRadius: '4px',
                  background: 'var(--bg-panel)', border: '1px solid var(--border)',
                  boxShadow: 'var(--glass-shadow)',
                }}
              >
                {CATEGORY_COLOR_PRESETS.map(c => (
                  <button
                    key={c}
                    type="button"
                    title={c}
                    onClick={() => pickColor(c)}
                    style={{
                      width: '14px', height: '14px', borderRadius: '50%',
                      background: c, cursor: 'pointer',
                      border: c === category.color ? '2px solid var(--text-primary)' : '1px solid var(--border)',
                    }}
                  />
                ))}
              </div>
            </>
          )}
        </span>
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
          <>
            <button
              title="이름 수정"
              onClick={startEdit}
              style={{ fontSize: '10px', color: 'var(--text-secondary)', padding: '0 2px', lineHeight: 1 }}
            >
              ✎
            </button>
            <button
              title="은하 삭제"
              onClick={handleDelete}
              style={{ fontSize: '10px', color: 'var(--text-secondary)', padding: '0 2px', lineHeight: 1 }}
              onMouseEnter={e => ((e.currentTarget as HTMLButtonElement).style.color = 'var(--text-primary)')}
              onMouseLeave={e => ((e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)')}
            >
              ✕
            </button>
          </>
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
              onDoubleClick={() => onDoubleClickNote(note.id)}
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
