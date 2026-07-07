import { useEffect, useState } from 'react'
import { useCategoriesStore } from '../../store/categoriesStore'
import { useNotesStore } from '../../store/notesStore'
import { CategoryItem, NOTE_DRAG_MIME } from './CategoryItem'

const GALAXY_COLORS = ['#3B5BDB', '#C2255C', '#2F9E44', '#E67700', '#7048E8', '#0C8599']

export function VoyageLog() {
  const { categories, fetchCategories, addCategory, loading } = useCategoriesStore()
  const { notes, fetchNotes, openNote, createNote, activeNote, setTab, moveNote,
    archivedNotes, archivedCount, fetchArchived, restoreNote, deleteNote } = useNotesStore()
  const [newCatName, setNewCatName] = useState('')
  const [showNewCat, setShowNewCat] = useState(false)
  const [catError, setCatError] = useState('')
  const [uncatDragOver, setUncatDragOver] = useState(false)
  const [blackholeOpen, setBlackholeOpen] = useState(false)

  useEffect(() => {
    fetchCategories().catch(console.error)
    fetchNotes().catch(console.error)
    fetchArchived().catch(console.error)
  }, [])

  const handleAddCategory = async () => {
    if (!newCatName.trim()) return
    setCatError('')
    try {
      const color = GALAXY_COLORS[categories.length % GALAXY_COLORS.length]
      await addCategory(newCatName.trim(), color)
      setNewCatName('')
      setShowNewCat(false)
    } catch (e: any) {
      setCatError('이미 존재하는 이름입니다')
    }
  }

  const handleCreateNote = async (categoryId: string) => {
    const title = `새 노트 ${notes.length + 1}`
    await createNote(title, categoryId).catch(console.error)
  }

  const handleSelectNote = (id: string) => {
    openNote(id)
    setTab('edit')
  }

  const handleUncatDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setUncatDragOver(false)
    const noteId = e.dataTransfer.getData(NOTE_DRAG_MIME)
    if (noteId) moveNote(noteId, null)
  }

  const notesByCategory = (catId: string) => notes.filter(n => n.category_id === catId)
  const uncategorized = notes.filter(n => !n.category_id)
  const favorites = notes.filter(n => n.is_favorite)

  if (loading && categories.length === 0) {
    return (
      <div className="flex-1 px-3 py-4 space-y-2">
        {[1, 2].map(i => (
          <div key={i} style={{ height: '24px', borderRadius: '3px', background: 'var(--bg-input)', opacity: 0.5 }} />
        ))}
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto py-2">
      <div className="px-3 py-1 flex items-center justify-between">
        <span style={{ fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
          항해일지
        </span>
        <button
          className="text-xs px-1.5 py-0.5"
          style={{ color: 'var(--text-secondary)', background: 'var(--bg-input)', borderRadius: '3px', fontSize: '11px' }}
          onClick={() => { setShowNewCat(s => !s); setCatError('') }}
        >
          + 은하
        </button>
      </div>

      {favorites.length > 0 && (
        <div className="mb-1 pb-1" style={{ borderBottom: '1px solid var(--glass-border)' }}>
          <div className="px-3 py-1" style={{
            fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase',
            color: '#E8B23A', opacity: 0.85,
          }}>
            ⚓ 기항지
          </div>
          {favorites.map(note => (
            <button
              key={note.id}
              className="w-full text-left truncate"
              style={{
                fontSize: '13px',
                color: activeNote?.id === note.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                borderLeft: activeNote?.id === note.id ? '2px solid #E8B23A' : '2px solid transparent',
                paddingLeft: activeNote?.id === note.id ? '14px' : '16px',
                paddingRight: '12px', paddingTop: '3px', paddingBottom: '3px',
                display: 'block', cursor: 'pointer',
              }}
              onClick={() => handleSelectNote(note.id)}
            >
              {note.title}
            </button>
          ))}
        </div>
      )}

      {showNewCat && (
        <div className="px-3 py-1">
          <div className="flex gap-1">
            <input
              autoFocus
              value={newCatName}
              onChange={e => setNewCatName(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') handleAddCategory()
                if (e.key === 'Escape') { setShowNewCat(false); setCatError('') }
              }}
              placeholder="카테고리명"
              style={{
                flex: 1,
                fontSize: '12px',
                padding: '3px 8px',
                borderRadius: '3px',
                background: 'var(--bg-input)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
                outline: 'none',
              }}
            />
            <button
              onClick={handleAddCategory}
              style={{ fontSize: '11px', color: 'var(--text-secondary)', padding: '0 6px' }}
            >
              추가
            </button>
          </div>
          {catError && (
            <p style={{ fontSize: '10px', color: '#C92A2A', marginTop: '2px' }}>{catError}</p>
          )}
        </div>
      )}

      {categories.length === 0 && !showNewCat && (
        <div className="flex flex-col items-center justify-center py-8 gap-3" style={{ color: 'var(--text-secondary)' }}>
          <svg width="32" height="32" viewBox="0 0 48 48" fill="none" style={{ opacity: 0.2 }}>
            <ellipse cx="24" cy="24" rx="22" ry="10" stroke="currentColor" strokeWidth="1.5" />
            <circle cx="24" cy="24" r="3" fill="currentColor" />
          </svg>
          <p style={{ fontSize: '12px', opacity: 0.6 }}>항해를 시작하세요</p>
          <button
            onClick={() => setShowNewCat(true)}
            style={{ fontSize: '11px', padding: '4px 12px', background: 'var(--bg-input)', borderRadius: '3px', color: 'var(--text-secondary)' }}
          >
            + 새 은하
          </button>
        </div>
      )}

      {categories.map(cat => (
        <CategoryItem
          key={cat.id}
          category={cat}
          notes={notesByCategory(cat.id)}
          onSelectNote={handleSelectNote}
          onCreateNote={handleCreateNote}
          onDropNote={noteId => moveNote(noteId, cat.id)}
          activeNoteId={activeNote?.id}
        />
      ))}

      {uncategorized.length > 0 && (
        <div className="mt-2 pt-2" style={{ borderTop: '1px solid var(--glass-border)' }}>
          <div
            className="px-3 py-1"
            style={{
              fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-secondary)',
              background: uncatDragOver ? 'var(--bg-input)' : undefined,
              outline: uncatDragOver ? '1px dashed var(--accent-line)' : undefined,
            }}
            onDragOver={e => {
              if (!e.dataTransfer.types.includes(NOTE_DRAG_MIME)) return
              e.preventDefault()
              setUncatDragOver(true)
            }}
            onDragLeave={() => setUncatDragOver(false)}
            onDrop={handleUncatDrop}
          >
            미분류
          </div>
          {uncategorized.map(note => (
            <button
              key={note.id}
              draggable
              onDragStart={e => e.dataTransfer.setData(NOTE_DRAG_MIME, note.id)}
              className="w-full text-left truncate"
              style={{
                fontSize: '13px',
                color: activeNote?.id === note.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                borderLeft: activeNote?.id === note.id ? '2px solid var(--accent-line)' : '2px solid transparent',
                paddingLeft: activeNote?.id === note.id ? '14px' : '16px',
                paddingRight: '12px',
                paddingTop: '3px',
                paddingBottom: '3px',
                display: 'block',
                cursor: 'grab',
              }}
              onClick={() => handleSelectNote(note.id)}
            >
              {note.title}
            </button>
          ))}
        </div>
      )}

      {archivedCount > 0 && (
        <div className="mt-2 pt-2" style={{ borderTop: '1px solid var(--glass-border)' }}>
          <button
            className="w-full text-left px-3 py-1 flex items-center gap-1.5"
            style={{
              fontSize: '10px', letterSpacing: '0.12em', textTransform: 'uppercase',
              color: 'var(--text-secondary)', opacity: 0.7,
            }}
            onClick={() => {
              setBlackholeOpen(o => !o)
              if (!blackholeOpen) fetchArchived().catch(console.error)
            }}
          >
            <span>🕳 블랙홀 ({archivedCount})</span>
            <span className="ml-auto" style={{ fontSize: '9px' }}>{blackholeOpen ? '▾' : '▸'}</span>
          </button>
          {blackholeOpen && archivedNotes.map(note => (
            <div key={note.id} className="flex items-center" style={{ paddingRight: '8px' }}>
              <span
                className="flex-1 truncate"
                style={{
                  fontSize: '12px', color: 'var(--text-secondary)', opacity: 0.6,
                  paddingLeft: '16px', paddingTop: '3px', paddingBottom: '3px',
                }}
              >
                {note.title}
              </span>
              <button
                title="복원"
                onClick={() => restoreNote(note.id)}
                style={{ fontSize: '10px', color: 'var(--text-secondary)', padding: '0 4px' }}
              >
                ↺
              </button>
              <button
                title="영구 삭제"
                onClick={() => {
                  if (confirm(`"${note.title}" 노트를 영구 삭제할까요? (.md 파일도 삭제됩니다)`)) {
                    deleteNote(note.id).then(() => fetchArchived()).catch(console.error)
                  }
                }}
                style={{ fontSize: '10px', color: '#C92A2A', padding: '0 4px' }}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
