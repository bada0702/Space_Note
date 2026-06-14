import { useEffect, useRef } from 'react'
import { useSearchStore } from '../../store/searchStore'
import { useNotesStore } from '../../store/notesStore'
import { useCategoriesStore } from '../../store/categoriesStore'

export function SearchPanel() {
  const { query, results, loading, setQuery, doSearch, setPanel } = useSearchStore()
  const { openNote, setTab } = useNotesStore()
  const { categories } = useCategoriesStore()
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  const catName = (id: string | null) =>
    categories.find(c => c.id === id)?.name ?? '미분류'
  const catColor = (id: string | null) =>
    categories.find(c => c.id === id)?.color ?? '#666677'

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') doSearch(query)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-app)' }}>
      {/* 헤더 */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{
          fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)',
          letterSpacing: '0.08em', marginBottom: 8,
        }}>
          ⊕ 항법 — 전문 검색
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKey}
            placeholder="노트 제목·내용 검색..."
            style={{
              flex: 1, padding: '6px 10px', borderRadius: 5,
              background: 'var(--bg-input)', color: 'var(--text-primary)',
              border: '1px solid var(--border)', fontSize: 13, outline: 'none',
            }}
          />
          <button
            onClick={() => doSearch(query)}
            style={{
              padding: '6px 14px', borderRadius: 5,
              background: 'var(--bg-input)', color: 'var(--text-secondary)',
              border: '1px solid var(--border)', cursor: 'pointer', fontSize: 12, fontWeight: 500,
            }}
          >
            검색
          </button>
        </div>
      </div>

      {/* 결과 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {loading && (
          <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: 12 }}>
            검색 중...
          </div>
        )}
        {!loading && results.length === 0 && query && (
          <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: 12, opacity: 0.6 }}>
            검색 결과 없음
          </div>
        )}
        {!loading && results.length === 0 && !query && (
          <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: 12, opacity: 0.5 }}>
            키워드를 입력하고 Enter 또는 검색 버튼을 누르세요
          </div>
        )}
        {results.map(r => (
          <button
            key={r.id}
            onClick={() => { openNote(r.id); setTab('edit'); setPanel(null) }}
            style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: '10px 16px',
              background: 'none', cursor: 'pointer', border: 'none',
              borderBottom: '1px solid var(--border)',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-input)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'none')}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
              <span style={{
                width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                background: catColor(r.category_id),
              }} />
              <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                {r.title}
              </span>
              <span style={{ fontSize: 10, color: 'var(--text-secondary)', marginLeft: 'auto', opacity: 0.6 }}>
                {catName(r.category_id)}
              </span>
            </div>
            {r.content_preview && (
              <div style={{
                fontSize: 11, color: 'var(--text-secondary)',
                overflow: 'hidden', display: '-webkit-box',
                WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                lineHeight: 1.5, paddingLeft: 12,
              }}>
                {r.content_preview}
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
