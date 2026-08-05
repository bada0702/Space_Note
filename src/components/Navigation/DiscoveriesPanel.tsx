import { useEffect, useRef, useState } from 'react'
import { useSearchStore } from '../../store/searchStore'
import { useNotesStore } from '../../store/notesStore'
import { useCategoriesStore } from '../../store/categoriesStore'
import { notesApi } from '../../api/notesApi'

export function DiscoveriesPanel() {
  const { discoveries, loading, loadDiscoveries, setPanel } = useSearchStore()
  const { activeNote, openNote, setTab, fetchNotes } = useNotesStore()
  const { categories } = useCategoriesStore()
  const [analyzing, setAnalyzing] = useState(false)
  const [notice, setNotice] = useState('')
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => { alive.current = false }
  }, [])

  useEffect(() => {
    loadDiscoveries(activeNote?.id)
  }, [activeNote?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // 내용 있는 노트의 pending이 모두 풀릴 때까지 폴링하며 진행 상태 안내
  const pollUntilDone = async (onProgress: (completed: number, total: number) => void): Promise<boolean> => {
    for (let i = 0; i < 180 && alive.current; i++) {
      const list = await notesApi.list()
      const total = list.filter(n => n.word_count > 0).length
      const pending = list.filter(n => n.analysis_status === 'pending' && n.word_count > 0).length
      const completed = total - pending

      onProgress(completed, total)

      if (pending === 0) return true
      await new Promise(r => setTimeout(r, 2000)) // 2초 주기 체크
    }
    return false
  }

  const runAnalyze = async (call: () => Promise<{ queued: number }>) => {
    setNotice('')
    setAnalyzing(true)
    try {
      const { queued } = await call()
      if (queued === 0) {
        setNotice('분석할 노트가 없습니다')
        return
      }
      setNotice(`분석 준비 중...`)
      
      const done = await pollUntilDone((completed, total) => {
        setNotice(`분석 진행 중: 전체 ${total}개 중 ${completed}개 완료 (${completed}/${total}개)`)
      })
      
      if (!alive.current) return
      await fetchNotes()
      await loadDiscoveries(activeNote?.id)
      
      if (!done) {
        setNotice('아직 분석이 진행 중입니다 — 잠시 후 새로고침을 눌러주세요')
        return
      }
      const failed = useNotesStore.getState().notes
        .filter(n => n.analysis_status === 'failed' && n.word_count > 0).length
      setNotice(
        failed > 0
          ? `${failed}개 분석 실패 — 잠시 후 다시 시도하세요`
          : '모든 노트의 분석 및 항로 연결이 완료되었습니다!',
      )
    } catch (e: any) {
      setNotice(
        String(e?.message).includes('API 400')
          ? 'AI 설정이 완료되지 않았습니다 (API 키를 저장하거나 로컬 Ollama 모델을 선택하세요)'
          : '분석 요청에 실패했습니다',
      )
    } finally {
      if (alive.current) setAnalyzing(false)
    }
  }

  const catColor = (id: string | null) =>
    categories.find(c => c.id === id)?.color ?? '#666677'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--bg-app)' }}>
      {/* 헤더 */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{
          fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)',
          letterSpacing: '0.08em', marginBottom: 2,
        }}>
          ⟡ 미개척 항로
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)', opacity: 0.6 }}>
          {activeNote
            ? `"${activeNote.title.slice(0, 20)}"와 연결된 노트`
            : 'AI가 발견한 노트 간 연결'}
        </div>
      </div>

      {/* 분석/새로고침 */}
      <div style={{ padding: '6px 16px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          {/* 자동항로분석 (Python) */}
          <button
            onClick={() => runAnalyze(() => notesApi.analyzeAllPython())}
            disabled={analyzing}
            style={{
              fontSize: 11, color: 'var(--text-primary)',
              background: 'var(--bg-input)', border: '1px solid var(--accent-line)',
              borderRadius: 4, padding: '3px 10px',
              cursor: analyzing ? 'wait' : 'pointer', opacity: analyzing ? 0.6 : 1,
            }}
            title="인공지능을 사용하지 않고 파이썬 엔진으로 빠르게 관련 키워드와 태그를 추출하여 항로를 찾습니다."
          >
            ⟡ 자동항로분석
          </button>

          {/* AI 항로분석 */}
          <button
            onClick={() => runAnalyze(() => notesApi.analyzeAll())}
            disabled={analyzing}
            style={{
              fontSize: 11, color: 'var(--text-primary)',
              background: 'var(--bg-input)', border: '1px solid var(--border)',
              borderRadius: 4, padding: '3px 10px',
              cursor: analyzing ? 'wait' : 'pointer', opacity: analyzing ? 0.6 : 1,
            }}
            title="거대언어모델(LLM)을 사용하여 맥락을 분석하고 의미적으로 관련된 항로를 찾습니다."
          >
            ✦ AI 항로분석
          </button>

          {activeNote && (
            <>
              {/* 이 노트 자동 분석 */}
              <button
                onClick={() => runAnalyze(() => notesApi.analyzeOnePython(activeNote.id))}
                disabled={analyzing}
                style={{
                  fontSize: 11, color: 'var(--text-secondary)',
                  background: 'var(--bg-input)', border: '1px solid var(--border)',
                  borderRadius: 4, padding: '3px 10px',
                  cursor: analyzing ? 'wait' : 'pointer', opacity: analyzing ? 0.6 : 1,
                }}
              >
                자동 분석 (이 노트)
              </button>

              {/* 이 노트 AI 분석 */}
              <button
                onClick={() => runAnalyze(() => notesApi.analyzeOne(activeNote.id))}
                disabled={analyzing}
                style={{
                  fontSize: 11, color: 'var(--text-secondary)',
                  background: 'var(--bg-input)', border: '1px solid var(--border)',
                  borderRadius: 4, padding: '3px 10px',
                  cursor: analyzing ? 'wait' : 'pointer', opacity: analyzing ? 0.6 : 1,
                }}
              >
                AI 분석 (이 노트)
              </button>
            </>
          )}

          <button
            onClick={() => loadDiscoveries(activeNote?.id)}
            disabled={analyzing}
            style={{
              fontSize: 11, color: 'var(--text-secondary)',
              background: 'var(--bg-input)', border: '1px solid var(--border)',
              borderRadius: 4, padding: '3px 10px', cursor: 'pointer',
              marginLeft: 'auto',
            }}
          >
            ↺ 새로고침
          </button>
        </div>
        {notice && (
          <div style={{ marginTop: 6, fontSize: 11, color: 'var(--accent-line)' }}>
            {notice}
          </div>
        )}
      </div>

      {/* 연결 목록 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {loading && (
          <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: 12 }}>
            탐색 중...
          </div>
        )}
        {!loading && discoveries.length === 0 && (
          <div style={{ padding: '40px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 28, marginBottom: 8, opacity: 0.3 }}>⟡</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', opacity: 0.6, lineHeight: 1.6 }}>
              아직 발견된 항로가 없습니다.<br />
              노트를 작성하면 AI가 자동으로 연결을 찾습니다.
            </div>
          </div>
        )}
        {discoveries.map(d => (
          <button
            key={d.note_id}
            onClick={() => { openNote(d.note_id); setTab('edit'); setPanel(null) }}
            style={{
              display: 'block', width: '100%', textAlign: 'left',
              padding: '10px 16px', background: 'none', cursor: 'pointer',
              border: 'none', borderBottom: '1px solid var(--border)',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-input)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'none')}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <span style={{
                width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                background: catColor(d.category_id),
              }} />
              <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                {d.title}
              </span>
              <span style={{
                marginLeft: 'auto', fontSize: 10,
                color: 'var(--accent-line)', fontWeight: 600,
              }}>
                {d.shared_count}개 공통
              </span>
            </div>
            {d.shared_entities.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, paddingLeft: 12 }}>
                {d.shared_entities.map(ent => (
                  <span
                    key={ent}
                    style={{
                      fontSize: 10, padding: '1px 6px',
                      background: 'var(--bg-input)', borderRadius: 10,
                      color: 'var(--text-secondary)', border: '1px solid var(--border)',
                    }}
                  >
                    {ent}
                  </span>
                ))}
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
