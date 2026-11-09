import { useEffect, useRef, useState } from 'react'
import { useSearchStore } from '../../store/searchStore'
import { useNotesStore } from '../../store/notesStore'
import { useCategoriesStore } from '../../store/categoriesStore'
import { notesApi } from '../../api/notesApi'
import { aiApi } from '../../api/aiApi'
import { EXPECTED_SECONDS, ProgressBar, etaText, useEstimatedProgress } from '../common/Progress'
import type { AnalyzeProgress, GraphStatus, Note } from '../../types'

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))
const pct = (done: number, total: number) => (total > 0 ? (done / total) * 100 : 0)

export function DiscoveriesPanel() {
  const { discoveries, loading, loadDiscoveries, setPanel } = useSearchStore()
  const { activeNote, openNote, setTab, fetchNotes } = useNotesStore()
  const { categories } = useCategoriesStore()
  const [notice, setNotice] = useState('')
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => { alive.current = false }
  }, [])

  useEffect(() => {
    loadDiscoveries(activeNote?.id)
  }, [activeNote?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const errorNotice = (e: any) =>
    String(e?.message).includes('API 400')
      ? 'AI 설정이 완료되지 않았습니다 (API 키를 저장하거나 로컬 Ollama 모델을 선택하세요)'
      : '분석 요청에 실패했습니다'

  // ── 일괄 분석: 서버 상태를 2초마다 읽어 키워드·지식 그래프 진행을 따로 보여 준다 ──
  // 패널을 닫았다 열어도 돌고 있는 작업을 이어서 보여 주고, 끝날 때까지 확인을 멈추지 않는다
  const [bulk, setBulk] = useState<{ keyword: AnalyzeProgress | null; graph: GraphStatus | null } | null>(null)
  const [rates, setRates] = useState<{ keyword: number | null; graph: number | null }>({ keyword: null, graph: null })
  const [starting, setStarting] = useState(false)
  const watching = useRef(false)

  const watchBulk = async (announce: boolean) => {
    if (watching.current) return
    watching.current = true
    let seen = announce
    let keywordSeen = false
    let first: { t: number; keyword: number; graph: number } | null = null
    setRates({ keyword: null, graph: null })
    try {
      while (alive.current) {
        const [k, g] = await Promise.all([
          notesApi.analyzeProgress().catch(() => null),
          aiApi.getGraphStatus().catch(() => null),
        ])
        const kRunning = !!k?.running
        const gRunning = !!g && g.pending > 0
        keywordSeen ||= kRunning
        if (!kRunning && !gRunning) {
          setBulk(null)
          if (seen) {
            await fetchNotes()
            await loadDiscoveries(useNotesStore.getState().activeNote?.id)
            const failed = (keywordSeen ? k?.failed ?? 0 : 0) + (g?.failed ?? 0)
            setNotice(failed > 0
              ? `분석 완료 — ${failed}개 실패 (설정 › 지식 그래프에서 이유를 확인하세요)`
              : '모든 노트의 분석 및 항로 연결이 완료되었습니다!')
          }
          return
        }
        seen = true
        // 처리 속도(분당)는 지켜보기 시작한 뒤의 실제 처리 수로 잰다
        const now = performance.now()
        const kDone = k ? k.done + k.failed : 0
        const gDone = g ? g.total - g.pending : 0
        if (!first) first = { t: now, keyword: kDone, graph: gDone }
        const minutes = (now - first.t) / 60000
        if (minutes >= 0.25) {
          setRates({ keyword: (kDone - first.keyword) / minutes, graph: (gDone - first.graph) / minutes })
        }
        setBulk({ keyword: keywordSeen ? k : null, graph: gRunning ? g : null })
        await sleep(2000)
      }
    } finally {
      watching.current = false
    }
  }

  useEffect(() => {
    watchBulk(false)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const runBulk = async (call: () => Promise<{ queued: number }>) => {
    setNotice('')
    setStarting(true)
    try {
      const { queued } = await call()
      if (queued === 0 && !watching.current) {
        setNotice('분석할 노트가 없습니다')
        return
      }
      watchBulk(true)
    } catch (e: any) {
      setNotice(errorNotice(e))
    } finally {
      if (alive.current) setStarting(false)
    }
  }

  // AI 분석은 키워드(채팅 모델)와 지식 그래프(추출 모델)를 함께 돌린다 — 한쪽만 되어도 진행
  const runAiBulk = () =>
    runBulk(async () => {
      const [k, g] = await Promise.allSettled([notesApi.analyzeAll(), aiApi.analyzeGraphMissing()])
      if (k.status === 'rejected' && g.status === 'rejected') throw k.reason
      const queued = (r: typeof k) => (r.status === 'fulfilled' ? r.value.queued : 0)
      return { queued: queued(k) + queued(g) }
    })

  // ── 노트 하나 분석: 실제 진행률을 알 수 없어 예상 시간 기준 %를 보여 준다 ──
  const [single, setSingle] = useState<{ label: string; expected: number } | null>(null)
  const singlePercent = useEstimatedProgress(!!single, single?.expected ?? 10)

  const runSingle = async (
    label: string,
    expected: number,
    call: () => Promise<Array<'keyword' | 'graph'>>,  // 실제로 시작된 작업
  ) => {
    if (!activeNote) return
    const id = activeNote.id
    setNotice('')
    setSingle({ label, expected })
    try {
      const started = await call()
      const pending = (n: Note) =>
        (started.includes('keyword') && n.analysis_status === 'pending') ||
        (started.includes('graph') && n.graph_status === 'pending')
      let note = await notesApi.get(id)
      for (let i = 0; i < 120 && alive.current && pending(note); i++) {
        await sleep(1000)
        note = await notesApi.get(id)
      }
      if (!alive.current) return
      await fetchNotes()
      await loadDiscoveries(useNotesStore.getState().activeNote?.id)
      if (pending(note)) setNotice('아직 분석이 진행 중입니다 — 잠시 후 새로고침을 눌러주세요')
      else if (note.analysis_status === 'failed' || note.graph_status === 'failed')
        setNotice(note.graph_error ? `분석 실패: ${note.graph_error}` : '분석 실패 — 잠시 후 다시 시도하세요')
      else setNotice('이 노트의 분석과 항로 연결이 완료되었습니다!')
    } catch (e: any) {
      setNotice(errorNotice(e))
    } finally {
      if (alive.current) setSingle(null)
    }
  }

  const runAiSingle = (id: string) =>
    runSingle('AI 분석 (이 노트)', EXPECTED_SECONDS.graphNote, async () => {
      const [k, g] = await Promise.allSettled([notesApi.analyzeOne(id), aiApi.analyzeGraphNote(id)])
      if (k.status === 'rejected' && g.status === 'rejected') throw k.reason
      return [...(k.status === 'fulfilled' ? ['keyword' as const] : []), ...(g.status === 'fulfilled' ? ['graph' as const] : [])]
    })

  const runPythonSingle = (id: string) =>
    runSingle('자동 분석 (이 노트)', EXPECTED_SECONDS.pythonNote, async () => {
      await notesApi.analyzeOnePython(id)
      return ['keyword']
    })

  const analyzing = starting || !!bulk || !!single

  const bulkDetail = (done: number, total: number, rate: number | null, failed: number) => {
    const eta = etaText(total - done, rate)
    return `${done}/${total} (${Math.round(pct(done, total))}%)${eta ? ` · ${eta}` : ''}${failed ? ` · 실패 ${failed}` : ''}`
  }

  const catColor = (id: string | null) =>
    categories.find(c => c.id === id)?.color ?? '#666677'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 헤더 */}
      <div className="sn-glass-bar" style={{ padding: '16px 24px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{
          fontFamily: 'var(--font-title)', fontSize: 19, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4,
        }}>
          미개척 항로
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', opacity: 0.6 }}>
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
            onClick={() => runBulk(notesApi.analyzeAllPython)}
            disabled={analyzing}
            style={{
              fontSize: 12, color: 'var(--text-primary)',
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
            onClick={runAiBulk}
            disabled={analyzing}
            style={{
              fontSize: 12, color: 'var(--text-primary)',
              background: 'var(--bg-input)', border: '1px solid var(--border)',
              borderRadius: 4, padding: '3px 10px',
              cursor: analyzing ? 'wait' : 'pointer', opacity: analyzing ? 0.6 : 1,
            }}
            title="거대언어모델(LLM)로 키워드와 지식 그래프(개념·관계)를 추출해, 개념을 공유하거나 관계로 이어진 노트를 항로로 찾습니다."
          >
            ✦ AI 항로분석
          </button>

          {activeNote && (
            <>
              {/* 이 노트 자동 분석 */}
              <button
                onClick={() => runPythonSingle(activeNote.id)}
                disabled={analyzing}
                style={{
                  fontSize: 12, color: 'var(--text-secondary)',
                  background: 'var(--bg-input)', border: '1px solid var(--border)',
                  borderRadius: 4, padding: '3px 10px',
                  cursor: analyzing ? 'wait' : 'pointer', opacity: analyzing ? 0.6 : 1,
                }}
              >
                자동 분석 (이 노트)
              </button>

              {/* 이 노트 AI 분석 */}
              <button
                onClick={() => runAiSingle(activeNote.id)}
                disabled={analyzing}
                style={{
                  fontSize: 12, color: 'var(--text-secondary)',
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
            disabled={starting || !!single} // 일괄 분석은 오래 걸리므로 도중에도 새로고침으로 중간 결과를 본다
            style={{
              fontSize: 12, color: 'var(--text-secondary)',
              background: 'var(--bg-input)', border: '1px solid var(--border)',
              borderRadius: 4, padding: '3px 10px', cursor: 'pointer',
              marginLeft: 'auto',
            }}
          >
            ↺ 새로고침
          </button>
        </div>
        {(bulk || single) && (
          <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {single && (
              <ProgressBar label={single.label} percent={singlePercent} detail={`약 ${Math.round(singlePercent)}% (예상)`} />
            )}
            {bulk?.keyword && (
              <ProgressBar
                label={bulk.keyword.kind === 'python' ? '키워드 (파이썬)' : '키워드'}
                percent={pct(bulk.keyword.done + bulk.keyword.failed, bulk.keyword.total)}
                detail={bulkDetail(bulk.keyword.done + bulk.keyword.failed, bulk.keyword.total, rates.keyword, bulk.keyword.failed)}
              />
            )}
            {bulk?.graph && (
              <ProgressBar
                label="지식 그래프"
                percent={pct(bulk.graph.total - bulk.graph.pending, bulk.graph.total)}
                detail={bulkDetail(bulk.graph.total - bulk.graph.pending, bulk.graph.total,
                  rates.graph || bulk.graph.rate_per_minute, bulk.graph.failed)}
              />
            )}
          </div>
        )}
        {notice && (
          <div style={{ marginTop: 6, fontSize: 12, color: 'var(--accent-line)' }}>
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
                marginLeft: 'auto', fontSize: 12,
                color: 'var(--accent-line)', fontWeight: 600,
              }}>
                {d.shared_count}개 공통
              </span>
            </div>
            {(d.shared_concepts.length > 0 || d.shared_entities.length > 0) && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, paddingLeft: 12 }}>
                {d.shared_concepts.map(c => (
                  <span
                    key={`c:${c}`}
                    title="지식 그래프 공유 개념"
                    style={{
                      fontSize: 12, padding: '1px 6px',
                      background: 'var(--bg-input)', borderRadius: 10,
                      color: 'var(--accent-line)', border: '1px solid var(--accent-line)',
                    }}
                  >
                    {c}
                  </span>
                ))}
                {d.shared_entities.filter(ent => !d.shared_concepts.includes(ent)).map(ent => (
                  <span
                    key={`k:${ent}`}
                    style={{
                      fontSize: 12, padding: '1px 6px',
                      background: 'var(--bg-input)', borderRadius: 10,
                      color: 'var(--text-secondary)', border: '1px solid var(--border)',
                    }}
                  >
                    {ent}
                  </span>
                ))}
              </div>
            )}
            {d.relations.length > 0 && (
              <div style={{ paddingLeft: 12, marginTop: 4, display: 'flex', flexDirection: 'column', gap: 2 }}>
                {d.relations.map(rel => (
                  <span key={rel} style={{ fontSize: 11, color: 'var(--text-secondary)', opacity: 0.85 }}>
                    {rel}
                    {d.evidence[rel] && (
                      <span style={{ display: 'block', paddingLeft: 10, fontStyle: 'italic', opacity: 0.8 }}>
                        “{d.evidence[rel]}”
                      </span>
                    )}
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
