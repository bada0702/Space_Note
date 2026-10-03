import { useEffect, useRef, useState } from 'react'
import type { Note } from '../../types'
import { useCategoriesStore } from '../../store/categoriesStore'
import { useNotesStore } from '../../store/notesStore'
import { useAIStore } from '../../store/aiStore'
import { CategoryItem, NoteItem, NOTE_DRAG_MIME } from './CategoryItem'

const GALAXY_COLORS = ['#3B5BDB', '#C2255C', '#2F9E44', '#E67700', '#7048E8', '#0C8599']

export function VoyageLog() {
  const { categories, fetchCategories, addCategory, loading } = useCategoriesStore()
  const { notes, fetchNotes, openNote, createNote, activeNote, setTab, moveNote,
    archivedNotes, archivedCount, fetchArchived, restoreNote, deleteNote, activeTab, importChatGPT } = useNotesStore()
  const { panelOpen, setPanelOpen } = useAIStore()
  const [newCatName, setNewCatName] = useState('')
  const [showNewCat, setShowNewCat] = useState(false)
  const [catError, setCatError] = useState('')
  const [uncatDragOver, setUncatDragOver] = useState(false)
  const [blackholeOpen, setBlackholeOpen] = useState(false)
  const [uncatOpen, setUncatOpen] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [importUrl, setImportUrl] = useState('')
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState('')
  const [lastClicks, setLastClicks] = useState<Record<string, number>>({})
  // 다중 선택: Shift 클릭 = 같은 목록 안에서 범위, Ctrl/⌘ 클릭 = 개별 토글, Delete 키 = 선택 삭제
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const anchorRef = useRef<string | null>(null)
  const listRef = useRef<HTMLDivElement>(null)

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

  const handleImport = async () => {
    const url = importUrl.trim()
    if (!url || importing) return
    setImporting(true)
    setImportError('')
    try {
      await importChatGPT(url)
      if (panelOpen) setPanelOpen(false)
      setImportUrl('')
      setShowImport(false)
    } catch (e) {
      // apiFetch 오류 메시지: "API 400: {"detail":"..."}" → detail만 보여준다
      const msg = e instanceof Error ? e.message : String(e)
      const detail = msg.match(/"detail":"([^"]+)"/)?.[1]
      setImportError(detail ?? msg)
    } finally {
      setImporting(false)
    }
  }

  const handleCreateNote = async (categoryId: string) => {
    const title = `새 노트 ${notes.length + 1}`
    await createNote(title, categoryId).catch(console.error)
  }

  const handleSelectNote = (id: string) => {
    openNote(id)
    // 성도/AI 채팅이 화면을 차지하고 있으면 노트를 열어도 보이지 않으므로 편집 화면으로 전환
    if (panelOpen) setPanelOpen(false)
    if (activeTab === 'starmap') setTab('edit')
  }

  const handleDoubleClickNote = (id: string) => {
    openNote(id)
    setTab('edit')
  }

  const handleNoteClick = (id: string) => {
    const now = Date.now()
    const lastClick = lastClicks[id] ?? 0
    if (now - lastClick < 300) {
      handleDoubleClickNote(id)
    } else {
      handleSelectNote(id)
    }
    setLastClicks(prev => ({ ...prev, [id]: now }))
  }

  const handleSelectClick = (id: string, e: React.MouseEvent, group: Note[]) => {
    // Safari는 버튼 클릭 시 포커스를 주지 않으므로 Delete 키를 받도록 목록에 포커스
    if (!listRef.current?.contains(document.activeElement)) listRef.current?.focus()
    const anchor = anchorRef.current
    if (e.shiftKey && anchor) {
      const ids = group.map(n => n.id)
      const a = ids.indexOf(anchor)
      const b = ids.indexOf(id)
      if (a >= 0 && b >= 0) {
        const [from, to] = a < b ? [a, b] : [b, a]
        setSelectedIds(new Set(ids.slice(from, to + 1)))
        return
      }
    }
    if (e.ctrlKey || e.metaKey) {
      setSelectedIds(prev => {
        const next = new Set(prev)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        return next
      })
      anchorRef.current = id
      return
    }
    anchorRef.current = id
    setSelectedIds(new Set([id]))
    handleSelectNote(id)
  }

  const handleListKeyDown = async (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setSelectedIds(new Set())
      return
    }
    if (e.key !== 'Delete' || selectedIds.size === 0) return
    // 입력창(새 은하 이름 등)에서 누른 Delete는 글자 지우기
    if ((e.target as HTMLElement).closest('input, textarea, [contenteditable="true"]')) return
    e.preventDefault()
    const targets = notes.filter(n => selectedIds.has(n.id))
    if (targets.length === 0) return
    const msg = targets.length === 1
      ? `"${targets[0].title}" 노트를 삭제할까요?`
      : `선택한 노트 ${targets.length}개를 삭제할까요?\n${targets.slice(0, 5).map(n => `· ${n.title}`).join('\n')}${targets.length > 5 ? `\n… 외 ${targets.length - 5}개` : ''}`
    if (!confirm(msg)) return
    const failed: string[] = []
    for (const n of targets) {
      try {
        await deleteNote(n.id)
      } catch (err) {
        console.error('note delete failed:', err)
        failed.push(n.title)
      }
    }
    setSelectedIds(new Set())
    anchorRef.current = null
    if (failed.length) alert(`삭제하지 못한 노트: ${failed.join(', ')}`)
  }

  const handleUncatDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setUncatDragOver(false)
    const noteId = e.dataTransfer.getData(NOTE_DRAG_MIME)
    if (noteId) moveNote(noteId, null)
  }

  const notesByCategory = (catId: string) => notes.filter(n => n.category_id === catId)
  const uncategorized = notes.filter(n => !n.category_id)
  const activeUncat = !!activeNote && uncategorized.some(n => n.id === activeNote.id)
  useEffect(() => {
    if (activeUncat) setUncatOpen(true)
  }, [activeUncat, activeNote?.id])
  const favorites = notes.filter(n => n.is_favorite)

  const noteRow = (note: typeof notes[number], opts: { draggable?: boolean } = {}) => (
    <button
      key={note.id}
      draggable={opts.draggable}
      onDragStart={opts.draggable ? e => e.dataTransfer.setData(NOTE_DRAG_MIME, note.id) : undefined}
      className="sn-row"
      aria-current={activeNote?.id === note.id ? 'true' : undefined}
      style={{ cursor: opts.draggable ? 'grab' : 'pointer' }}
      onClick={() => handleNoteClick(note.id)}
    >
      <span className="sn-row-text">{note.title}</span>
    </button>
  )

  if (loading && categories.length === 0) {
    return (
      <div className="flex-1 px-4 py-4 space-y-2">
        {[1, 2, 3].map(i => (
          <div key={i} style={{ height: '22px', borderRadius: '4px', background: 'var(--bg-input)', opacity: 0.6 }} />
        ))}
      </div>
    )
  }

  return (
    <div
      ref={listRef}
      tabIndex={-1}
      onKeyDown={handleListKeyDown}
      className="flex-1 overflow-y-auto"
      style={{ padding: '10px 0', outline: 'none' }}
    >
      <div className="sn-label" style={{ paddingRight: '10px' }}>
        <span style={{ flex: 1 }}>항해일지</span>
        <button
          className="sn-icon-btn"
          style={{ width: 'auto', padding: '0 6px', fontWeight: 500 }}
          onClick={() => { setShowNewCat(s => !s); setCatError('') }}
          title="새 은하(카테고리) 만들기"
        >
          + 은하
        </button>
        <button
          className="sn-icon-btn"
          style={{ width: 'auto', padding: '0 6px', fontWeight: 500 }}
          onClick={() => { setShowImport(s => !s); setImportError('') }}
          title="ChatGPT 공유 링크로 노트 가져오기"
        >
          ⤓ GPT
        </button>
      </div>

      {showImport && (
        <div style={{ padding: '4px 10px 8px 16px' }}>
          <div className="flex gap-1">
            <input
              autoFocus
              className="sn-input"
              value={importUrl}
              onChange={e => setImportUrl(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') handleImport()
                if (e.key === 'Escape') { setShowImport(false); setImportError('') }
              }}
              placeholder="https://chatgpt.com/share/..."
              disabled={importing}
              style={{ flex: 1, minWidth: 0 }}
            />
            <button className="sn-btn" onClick={handleImport} disabled={importing || !importUrl.trim()}>
              {importing ? '가져오는 중…' : '가져오기'}
            </button>
          </div>
          {importError && (
            <p role="alert" style={{ fontSize: 'var(--fs-xs)', color: 'var(--danger)', marginTop: '4px' }}>{importError}</p>
          )}
        </div>
      )}

      {showNewCat && (
        <div style={{ padding: '4px 10px 8px 16px' }}>
          <div className="flex gap-1">
            <input
              autoFocus
              className="sn-input"
              value={newCatName}
              onChange={e => setNewCatName(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') handleAddCategory()
                if (e.key === 'Escape') { setShowNewCat(false); setCatError('') }
              }}
              placeholder="은하 이름"
              style={{ flex: 1, minWidth: 0 }}
            />
            <button className="sn-btn" onClick={handleAddCategory}>만들기</button>
          </div>
          {catError && (
            <p role="alert" style={{ fontSize: 'var(--fs-xs)', color: 'var(--danger)', marginTop: '4px' }}>{catError}</p>
          )}
        </div>
      )}

      {favorites.length > 0 && (
        <div style={{ marginBottom: '10px' }}>
          <div className="sn-label" style={{ color: 'var(--star)' }}>
            <span aria-hidden="true">★</span> 기항지 <span className="sn-count">{favorites.length}</span>
          </div>
          {favorites.map(note => noteRow(note))}
        </div>
      )}

      {categories.length === 0 && !showNewCat && (
        <div className="flex flex-col items-center justify-center py-8 gap-3" style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>
          <svg width="36" height="36" viewBox="0 0 48 48" fill="none" style={{ opacity: 0.35 }} aria-hidden="true">
            <ellipse cx="24" cy="24" rx="22" ry="10" stroke="currentColor" strokeWidth="1.5" />
            <circle cx="24" cy="24" r="3" fill="var(--star)" />
          </svg>
          <p style={{ fontSize: 'var(--fs-sm)', padding: '0 20px' }}>은하를 만들어 노트를 분류하세요</p>
          <button className="sn-btn" onClick={() => setShowNewCat(true)}>+ 새 은하</button>
        </div>
      )}

      {categories.map(cat => (
        <CategoryItem
          key={cat.id}
          category={cat}
          notes={notesByCategory(cat.id)}
          selectedIds={selectedIds}
          onSelectClick={handleSelectClick}
          onDoubleClickNote={handleDoubleClickNote}
          onCreateNote={handleCreateNote}
          onDropNote={noteId => moveNote(noteId, cat.id)}
          activeNoteId={activeNote?.id}
        />
      ))}

      {uncategorized.length > 0 && (
        <div style={{ marginTop: '10px' }}>
          <div
            role="button"
            tabIndex={0}
            aria-expanded={uncatOpen}
            className="sn-label"
            style={{
              cursor: 'pointer',
              background: uncatDragOver ? 'var(--star-soft)' : undefined,
              outline: uncatDragOver ? '1px dashed var(--star)' : undefined,
            }}
            onClick={() => setUncatOpen(o => !o)}
            onKeyDown={e => e.key === 'Enter' && setUncatOpen(o => !o)}
            onDragOver={e => {
              if (!e.dataTransfer.types.includes(NOTE_DRAG_MIME)) return
              e.preventDefault()
              setUncatDragOver(true)
            }}
            onDragLeave={() => setUncatDragOver(false)}
            onDrop={handleUncatDrop}
          >
            <span aria-hidden="true" style={{ width: '8px', fontSize: '10px', color: 'var(--text-tertiary)' }}>{uncatOpen ? '▾' : '▸'}</span>
            미분류 <span className="sn-count">{uncategorized.length}</span>
          </div>
          {uncatOpen && <ul>
            {uncategorized.map(note => (
              <NoteItem
                key={note.id}
                note={note}
                indent={16}
                isActive={activeNote?.id === note.id}
                isSelected={selectedIds.has(note.id)}
                onSelect={e => handleSelectClick(note.id, e, uncategorized)}
                onDoubleClick={() => handleDoubleClickNote(note.id)}
              />
            ))}
          </ul>}
        </div>
      )}

      {archivedCount > 0 && (
        <div style={{ marginTop: '10px', paddingTop: '6px', borderTop: '1px solid var(--border)' }}>
          <button
            className="sn-label"
            style={{ width: '100%', textAlign: 'left', cursor: 'pointer' }}
            aria-expanded={blackholeOpen}
            onClick={() => {
              setBlackholeOpen(o => !o)
              if (!blackholeOpen) fetchArchived().catch(console.error)
            }}
          >
            <span aria-hidden="true">◐</span> 블랙홀 <span className="sn-count">{archivedCount}</span>
            <span className="ml-auto" aria-hidden="true">{blackholeOpen ? '▾' : '▸'}</span>
          </button>
          {blackholeOpen && archivedNotes.map(note => (
            <div key={note.id} className="sn-row" style={{ cursor: 'default', paddingRight: '8px' }}>
              <span className="sn-row-text" style={{ color: 'var(--text-tertiary)' }}>{note.title}</span>
              <button
                className="sn-icon-btn"
                title="복원"
                aria-label={`"${note.title}" 복원`}
                onClick={() => restoreNote(note.id)}
              >
                ↺
              </button>
              <button
                className="sn-icon-btn is-danger"
                title="영구 삭제"
                aria-label={`"${note.title}" 영구 삭제`}
                onClick={() => {
                  if (confirm(`"${note.title}" 노트를 영구 삭제할까요? (.md 파일도 삭제됩니다)`)) {
                    deleteNote(note.id).then(() => fetchArchived()).catch(console.error)
                  }
                }}
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
