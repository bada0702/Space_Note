import { useEffect, useState } from 'react'
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
  onDoubleClickNote: (id: string) => void
  activeNoteId?: string
  onCreateNote: (categoryId: string) => void
  onDropNote: (noteId: string) => void
  selectedIds: Set<string>
  onSelectClick: (id: string, e: React.MouseEvent, group: Note[]) => void
}

export function NoteItem({
  note,
  isActive,
  isSelected,
  onSelect,
  onDoubleClick,
  indent = 32,
}: {
  note: Note
  isActive: boolean
  isSelected: boolean
  onSelect: (e: React.MouseEvent) => void
  onDoubleClick: () => void
  indent?: number
}) {
  const { deleteNote, toggleFavorite, archiveNote } = useNotesStore()
  const [lastClick, setLastClick] = useState(0)

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (confirm(`"${note.title}" 노트를 삭제할까요?`)) {
      deleteNote(note.id)
    }
  }

  const handleClick = (e: React.MouseEvent) => {
    const now = Date.now()
    // Shift/Ctrl 클릭은 다중 선택 전용 — 더블클릭(편집 열기)으로 취급하지 않는다
    if (now - lastClick < 300 && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
      onDoubleClick()
    } else {
      onSelect(e)
    }
    setLastClick(now)
  }

  return (
    <li className="sn-row-wrap">
      <button
        draggable
        onDragStart={e => e.dataTransfer.setData(NOTE_DRAG_MIME, note.id)}
        className="sn-row"
        aria-current={isActive ? 'true' : undefined}
        aria-selected={isSelected}
        data-note-id={note.id}
        style={{ paddingLeft: `${indent}px`, cursor: 'grab' }}
        onClick={handleClick}
      >
        <span className="sn-row-text">{note.title}</span>
        {note.is_favorite && <span className="sn-fav-mark" aria-label="기항지">★</span>}
      </button>
      <div className="sn-row-actions">
        <button
          className="sn-icon-btn"
          title={note.is_favorite ? '기항지 해제' : '기항지로 지정'}
          aria-label={note.is_favorite ? '기항지 해제' : '기항지로 지정'}
          onClick={e => { e.stopPropagation(); toggleFavorite(note.id) }}
          style={note.is_favorite ? { color: 'var(--star)' } : undefined}
        >
          {note.is_favorite ? '★' : '☆'}
        </button>
        <button
          className="sn-icon-btn"
          title="블랙홀로 보내기 (보관)"
          aria-label="블랙홀로 보내기 (보관)"
          onClick={e => { e.stopPropagation(); archiveNote(note.id) }}
        >
          ◐
        </button>
        <button className="sn-icon-btn is-danger" title="삭제" aria-label="삭제" onClick={handleDelete}>
          ✕
        </button>
      </div>
    </li>
  )
}

export function CategoryItem({ category, notes, onDoubleClickNote, activeNoteId, onCreateNote, onDropNote, selectedIds, onSelectClick }: Props) {
  // 처음엔 은하 이름만 보이고, 눌러야 노트 목록이 펼쳐진다
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [nameValue, setNameValue] = useState(category.name)
  const [dragOver, setDragOver] = useState(false)
  const [colorPickerOpen, setColorPickerOpen] = useState(false)
  const { setTab, setStarMapFilter } = useNotesStore()
  const { updateCategory, deleteCategory } = useCategoriesStore()

  // 성도·검색 등에서 이 은하의 노트를 열면 목록을 펼쳐 위치를 보여준다
  const hasActive = !!activeNoteId && notes.some(n => n.id === activeNoteId)
  useEffect(() => {
    if (hasActive) setOpen(true)
  }, [hasActive, activeNoteId])

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
    <div style={{ marginBottom: '6px' }}>
      <div
        role="button"
        tabIndex={0}
        aria-expanded={open}
        className="sn-cat-head"
        style={{
          background: dragOver ? 'var(--star-soft)' : undefined,
          outline: dragOver ? '1px dashed var(--star)' : undefined,
        }}
        onClick={() => !editing && setOpen(o => !o)}
        onKeyDown={e => e.key === 'Enter' && !editing && setOpen(o => !o)}
        onDragOver={handleDragOver}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <span aria-hidden="true" style={{ width: '8px', fontSize: '10px', color: 'var(--text-tertiary)' }}>{open ? '▾' : '▸'}</span>
        <span style={{ position: 'relative', display: 'inline-flex' }}>
          <button
            type="button"
            title="은하 색상 변경"
            aria-label="은하 색상 변경"
            onClick={e => { e.stopPropagation(); setColorPickerOpen(o => !o) }}
            style={{
              width: '9px', height: '9px', borderRadius: '50%', cursor: 'pointer',
              background: category.color ?? 'var(--text-tertiary)',
              boxShadow: `0 0 0 3px color-mix(in srgb, ${category.color ?? 'transparent'} 22%, transparent)`,
            }}
          />
          {colorPickerOpen && (
            <>
              <div
                style={{ position: 'fixed', inset: 0, zIndex: 10 }}
                onClick={e => { e.stopPropagation(); setColorPickerOpen(false) }}
              />
              <div
                onClick={e => e.stopPropagation()}
                style={{
                  position: 'absolute', top: '16px', left: '-6px', zIndex: 11,
                  display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '6px',
                  padding: '8px', borderRadius: '8px',
                  background: 'var(--bg-panel)', border: '1px solid var(--border)',
                  boxShadow: 'var(--glass-shadow)',
                }}
              >
                {CATEGORY_COLOR_PRESETS.map(c => (
                  <button
                    key={c}
                    type="button"
                    title={c}
                    aria-label={`색상 ${c}`}
                    onClick={() => pickColor(c)}
                    style={{
                      width: '18px', height: '18px', borderRadius: '50%',
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
            className="sn-input"
            value={nameValue}
            onChange={e => setNameValue(e.target.value)}
            onClick={e => e.stopPropagation()}
            onBlur={saveName}
            onKeyDown={e => {
              e.stopPropagation()
              if (e.key === 'Enter') saveName()
              if (e.key === 'Escape') setEditing(false)
            }}
            style={{ flex: 1, minWidth: 0, padding: '2px 6px' }}
          />
        ) : (
          <span className="sn-row-text" style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {category.name}
          </span>
        )}
        {!editing && (
          <>
            <span className="sn-count-cat">{notes.length}</span>
            <span className="sn-cat-tools">
              <button className="sn-icon-btn" title="성도에서 이 은하 보기" aria-label="성도에서 이 은하 보기" onClick={showInStarMap}>✦</button>
              <button className="sn-icon-btn" title="이름 수정" aria-label="이름 수정" onClick={startEdit}>✎</button>
              <button className="sn-icon-btn is-danger" title="은하 삭제" aria-label="은하 삭제" onClick={handleDelete}>✕</button>
            </span>
          </>
        )}
      </div>

      {open && (
        <ul>
          <li>
            <button
              className="sn-row"
              style={{ paddingLeft: '32px', color: 'var(--text-tertiary)', fontSize: 'var(--fs-xs)', minHeight: '26px' }}
              onClick={() => onCreateNote(category.id)}
            >
              + 새 노트
            </button>
          </li>
          {notes.map(note => (
            <NoteItem
              key={note.id}
              note={note}
              isActive={activeNoteId === note.id}
              isSelected={selectedIds.has(note.id)}
              onSelect={e => onSelectClick(note.id, e, notes)}
              onDoubleClick={() => onDoubleClickNote(note.id)}
            />
          ))}
        </ul>
      )}
    </div>
  )
}
