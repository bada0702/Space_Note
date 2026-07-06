import { useEffect, useState } from 'react'
import { useNotesStore } from '../../store/notesStore'
import { useCategoriesStore } from '../../store/categoriesStore'
import { useSearchStore } from '../../store/searchStore'
import { tagsApi } from '../../api/tagsApi'
import type { TagSummary, TaggedNote } from '../../types'

export function TagsPanel() {
  const { openNote, setTab, setStarMapFilter } = useNotesStore()
  const { categories } = useCategoriesStore()
  const { setPanel } = useSearchStore()
  const [tags, setTags] = useState<TagSummary[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [notes, setNotes] = useState<TaggedNote[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    tagsApi.list().then(setTags).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selected) { setNotes([]); return }
    setLoading(true)
    tagsApi.notesForTag(selected).then(setNotes).finally(() => setLoading(false))
  }, [selected])

  const catColor = (id: string | null) =>
    categories.find(c => c.id === id)?.color ?? '#666677'

  const showInStarMap = () => {
    if (!selected) return
    setStarMapFilter({ type: 'tag', value: selected })
    setTab('starmap')
    setPanel(null)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-app)' }}>
      {/* 헤더 */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{
          fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)',
          letterSpacing: '0.08em', marginBottom: 2,
        }}>
          # 태그
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', opacity: 0.6 }}>
          {selected ? `#${selected} 가 붙은 노트` : '본문에 #태그를 적으면 자동으로 모입니다'}
        </div>
      </div>

      {selected && (
        <div style={{ padding: '6px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              onClick={() => setSelected(null)}
              style={{
                fontSize: 11, color: 'var(--text-secondary)',
                background: 'var(--bg-input)', border: '1px solid var(--border)',
                borderRadius: 4, padding: '3px 10px', cursor: 'pointer',
              }}
            >
              ← 전체 태그
            </button>
            <button
              onClick={showInStarMap}
              style={{
                fontSize: 11, color: 'var(--text-primary)',
                background: 'var(--bg-input)', border: '1px solid var(--accent-line)',
                borderRadius: 4, padding: '3px 10px', cursor: 'pointer',
              }}
            >
              ✦ 성도에서 보기
            </button>
          </div>
        </div>
      )}

      {/* 목록 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {loading && (
          <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: 12 }}>
            불러오는 중...
          </div>
        )}

        {!loading && !selected && tags.length === 0 && (
          <div style={{ padding: '40px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 28, marginBottom: 8, opacity: 0.3 }}>#</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', opacity: 0.6, lineHeight: 1.6 }}>
              아직 태그가 없습니다.<br />
              노트 본문에 #태그 를 적어보세요.
            </div>
          </div>
        )}

        {!loading && !selected && tags.map(t => (
          <button
            key={t.tag}
            onClick={() => setSelected(t.tag)}
            style={{
              display: 'flex', alignItems: 'center', width: '100%', textAlign: 'left',
              padding: '8px 16px', background: 'none', cursor: 'pointer',
              border: 'none', borderBottom: '1px solid var(--border)',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-input)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'none')}
          >
            <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
              #{t.tag}
            </span>
            <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--accent-line)', fontWeight: 600 }}>
              {t.count}개 노트
            </span>
          </button>
        ))}

        {!loading && selected && notes.map(n => (
          <button
            key={n.id}
            onClick={() => { openNote(n.id); setTab('edit'); setPanel(null) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, width: '100%', textAlign: 'left',
              padding: '8px 16px', background: 'none', cursor: 'pointer',
              border: 'none', borderBottom: '1px solid var(--border)',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-input)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'none')}
          >
            <span style={{
              width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
              background: catColor(n.category_id),
            }} />
            <span style={{ fontSize: 13, color: 'var(--text-primary)' }}>{n.title}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
