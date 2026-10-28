import { useEffect, useMemo, useState } from 'react'
import { useNotesStore } from '../../store/notesStore'
import { useCategoriesStore } from '../../store/categoriesStore'
import { useSearchStore } from '../../store/searchStore'
import { constellationsApi } from '../../api/constellationsApi'
import type { ConstellationSummary, ConstellationNote } from '../../types'

const norm = (s: string) => s.normalize('NFKC').replace(/[\s\-_./·]+/g, '').toLowerCase()

/**
 * 별자리 이름(제목)만 찾는다 — 이름이 검색어로 시작하거나 이름 속 단어가 검색어로 시작.
 * 동의어나 단어 중간 글자('php' → LangGraph)는 보지 않는다. 정확히 같은 이름 → 시작 → 단어 순.
 * 별자리는 수백 개라 한 번 받아 두고 입력할 때마다 바로 거른다 — 서버 왕복이 없어 지연이 없다.
 */
function searchConstellations(items: ConstellationSummary[], query: string): ConstellationSummary[] {
  const q = norm(query)
  if (!q) return items
  const word = ' ' + query.trim().toLowerCase().replace(/\s+/g, ' ')
  const ranked: [number, ConstellationSummary][] = []
  for (const t of items) {
    const n = norm(t.name)
    const rank = n === q ? 0 : n.startsWith(q) ? 1 : (' ' + t.name.toLowerCase()).includes(word) ? 2 : -1
    if (rank >= 0) ranked.push([rank, t])
  }
  return ranked.sort((a, b) => a[0] - b[0]).map(([, t]) => t)  // 같은 순위 안에서는 노트 수 순서 유지
}

/** 별자리: 여러 은하에 흩어진 노트들을 지식 그래프 개념 하나로 잇는다 */
export function ConstellationsPanel() {
  const { openNote, setTab, setStarMapFilter } = useNotesStore()
  const { categories } = useCategoriesStore()
  const { setPanel } = useSearchStore()
  const [items, setItems] = useState<ConstellationSummary[]>([])
  const [selected, setSelected] = useState<ConstellationSummary | null>(null)
  const [notes, setNotes] = useState<ConstellationNote[]>([])
  const [loading, setLoading] = useState(false)
  const [query, setQuery] = useState('')
  const shown = useMemo(() => searchConstellations(items, query), [items, query])

  useEffect(() => {
    setLoading(true)
    constellationsApi.list().then(setItems).finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selected) { setNotes([]); return }
    setLoading(true)
    constellationsApi.notes(selected.id).then(setNotes).finally(() => setLoading(false))
  }, [selected])

  const catColor = (id: string | null) =>
    categories.find(c => c.id === id)?.color ?? '#666677'

  const showInStarMap = () => {
    if (!selected) return
    setStarMapFilter({ type: 'constellation', value: selected.id, label: selected.name })
    setTab('starmap')
    setPanel(null)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 헤더 */}
      <div className="sn-glass-bar" style={{ padding: '16px 24px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{
          fontFamily: 'var(--font-title)', fontSize: 19, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4,
        }}>
          {selected ? `✧ ${selected.name}` : '별자리'}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', opacity: 0.6 }}>
          {selected
            ? `노트 ${selected.note_count}개 · 은하 ${selected.galaxy_count}개에 걸친 별자리`
            : '여러 노트에 걸친 핵심 개념을 지식 그래프가 찾아 이어 줍니다'}
        </div>
      </div>

      {!selected && (
        <div style={{ padding: '8px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          <input
            type="search"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="별자리 이름 검색"
            aria-label="별자리 검색"
            style={{
              width: '100%', boxSizing: 'border-box', padding: '6px 10px', fontSize: 13,
              background: 'var(--bg-input)', color: 'var(--text-primary)',
              border: '1px solid var(--border)', borderRadius: 5,
            }}
          />
        </div>
      )}

      {selected && (
        <div style={{ padding: '6px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              onClick={() => setSelected(null)}
              style={{
                fontSize: 12, color: 'var(--text-secondary)',
                background: 'var(--bg-input)', border: '1px solid var(--border)',
                borderRadius: 4, padding: '3px 10px', cursor: 'pointer',
              }}
            >
              ← 전체 별자리
            </button>
            <button
              onClick={showInStarMap}
              style={{
                fontSize: 12, color: 'var(--text-primary)',
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

        {!loading && !selected && items.length > 0 && shown.length === 0 && (
          <div style={{ padding: '40px 16px', textAlign: 'center', fontSize: 12, color: 'var(--text-secondary)', opacity: 0.6 }}>
            '{query.trim()}'(으)로 시작하는 별자리가 없습니다.
          </div>
        )}

        {!loading && !selected && items.length === 0 && (
          <div style={{ padding: '40px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 28, marginBottom: 8, opacity: 0.3 }}>✧</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', opacity: 0.6, lineHeight: 1.6 }}>
              아직 별자리가 없습니다.<br />
              설정의 지식 그래프에서 노트 분석을 시작하면 나타납니다.
            </div>
          </div>
        )}

        {!loading && !selected && shown.map(t => (
          <button
            key={t.id}
            onClick={() => setSelected(t)}
            style={{
              display: 'flex', alignItems: 'center', width: '100%', textAlign: 'left',
              padding: '8px 16px', background: 'none', cursor: 'pointer',
              border: 'none', borderBottom: '1px solid var(--border)',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-input)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'none')}
          >
            <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
              {t.name}
            </span>
            <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--text-tertiary)' }}>{t.type}</span>
            <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--accent-line)', fontWeight: 600 }}>
              노트 {t.note_count}
            </span>
            <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--text-secondary)', minWidth: 44, textAlign: 'right' }}>
              은하 {t.galaxy_count}
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
