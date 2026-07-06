import { useNotesStore } from '../../store/notesStore'
import { formatDateTime } from '../../utils/dateFormat'
import type { EditorTab } from '../../types'

const TABS: { id: EditorTab; label: string }[] = [
  { id: 'edit', label: '편집' },
  { id: 'preview', label: '미리보기' },
  { id: 'starmap', label: '성도' },
]

export function EditorTabs() {
  const { activeNote, activeTab, setTab, setStarMapFilter, deleteNote } = useNotesStore()

  if (!activeNote) return null

  const handleDelete = () => {
    if (confirm(`"${activeNote.title}" 노트를 삭제할까요?`)) {
      deleteNote(activeNote.id)
    }
  }

  return (
    <div className="glass glass-bar flex items-center px-4 gap-3">
      {/* 제목 | 날짜 시간 */}
      <div className="flex items-center gap-2 py-2.5 min-w-0 flex-1">
        <span
          className="truncate"
          style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', flexShrink: 0, maxWidth: '200px' }}
        >
          {activeNote.title}
        </span>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)', flexShrink: 0 }}>|</span>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
          {formatDateTime(activeNote.created_at)}
        </span>
      </div>

      {/* 탭 버튼 */}
      <div className="flex items-center gap-0">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => {
              if (tab.id === 'starmap') {
                setStarMapFilter(activeNote?.category_id ? { type: 'category', value: activeNote.category_id } : null)
              }
              setTab(tab.id)
            }}
            className="px-3 py-2.5"
            style={{
              fontSize: '12px',
              color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-secondary)',
              borderBottom: activeTab === tab.id ? '2px solid var(--accent-line)' : '2px solid transparent',
              whiteSpace: 'nowrap',
            }}
          >
            {tab.label}
          </button>
        ))}
        <div style={{ width: '1px', height: '14px', background: 'var(--border)', margin: '0 8px' }} />
        <button
          onClick={handleDelete}
          style={{
            fontSize: '11px',
            color: 'var(--text-secondary)',
            padding: '2px 8px',
            borderRadius: '3px',
            border: '1px solid var(--border)',
            whiteSpace: 'nowrap',
          }}
          onMouseEnter={e => {
            ;(e.currentTarget as HTMLButtonElement).style.color = '#C92A2A'
            ;(e.currentTarget as HTMLButtonElement).style.borderColor = '#C92A2A'
          }}
          onMouseLeave={e => {
            ;(e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)'
            ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border)'
          }}
        >
          삭제
        </button>
      </div>
    </div>
  )
}
