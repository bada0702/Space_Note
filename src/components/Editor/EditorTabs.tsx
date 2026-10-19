import { useState, useEffect, useRef } from 'react'
import { useNotesStore } from '../../store/notesStore'
import { formatDateTime } from '../../utils/dateFormat'
import { notesApi } from '../../api/notesApi'
import { searchApi } from '../../api/searchApi'
import type { EditorTab } from '../../types'

export function EditorTabs() {
  const { activeNote, activeTab, setTab, setStarMapFilter, deleteNote, renameNote, toggleFavorite } = useNotesStore()
  const [titleValue, setTitleValue] = useState('')
  const titleRef = useRef<HTMLInputElement>(null)
  const [routeBusy, setRouteBusy] = useState(false)
  const [routeNotice, setRouteNotice] = useState('')

  // activeNote가 바뀌면 제목 동기화
  useEffect(() => {
    if (activeNote) {
      setTitleValue(activeNote.title)
      // 새 노트면 제목 필드 자동 포커스
      if (/^새 노트/.test(activeNote.title)) {
        setTimeout(() => titleRef.current?.select(), 50)
      }
    }
    setRouteNotice('')
  }, [activeNote?.id])

  if (!activeNote) return null

  // 파이썬 엔진으로 이 노트의 키워드·태그를 다시 뽑는다 — 공유 키워드가 생기면 성도 항로가 자동으로 이어진다
  const handleRouteAnalyze = async () => {
    const id = activeNote.id
    setRouteBusy(true)
    setRouteNotice('항로 분석 중...')
    try {
      await notesApi.analyzeOnePython(id)
      let status = 'pending'
      for (let i = 0; i < 30 && status === 'pending'; i++) {
        await new Promise(r => setTimeout(r, 1000))
        status = (await notesApi.get(id)).analysis_status
      }
      if (useNotesStore.getState().activeNote?.id !== id) return
      if (status === 'pending') setRouteNotice('분석이 아직 진행 중입니다')
      else if (status === 'failed') setRouteNotice('항로 분석 실패')
      else {
        // 성도와 같은 기준(노트당 상한 적용)으로 이 노트에 이어진 항로 수를 센다
        const routes = await searchApi.discoveryRoutes()
        const linked = routes.filter(r => r.note_a === id || r.note_b === id).length
        setRouteNotice(linked ? `항로 ${linked}개 연결됨` : '연결할 노트를 찾지 못했습니다')
      }
    } catch {
      setRouteNotice('항로 분석 요청 실패')
    } finally {
      setRouteBusy(false)
    }
  }

  const handleTitleBlur = () => {
    if (activeNote && titleValue.trim() && titleValue !== activeNote.title) {
      renameNote(activeNote.id, titleValue)
    }
  }

  const handleTitleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.currentTarget.blur()
    }
    if (e.key === 'Escape') {
      setTitleValue(activeNote?.title ?? '')
      e.currentTarget.blur()
    }
  }

  const handleDelete = () => {
    if (confirm(`"${activeNote.title}" 노트를 삭제할까요?`)) {
      deleteNote(activeNote.id)
    }
  }

  const handlePrint = () => {
    if (!activeNote) return
    const content = activeNote.content || ""
    const escapeHtml = (s: string) => s.replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const title = escapeHtml(activeNote.title)
    const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>${title}</title>
  <style>
    body { font-family: 'Pretendard', 'Inter', sans-serif; font-size: 14px; line-height: 1.8; max-width: 800px; margin: 40px auto; color: #0a0a0a; }
    h1 { font-size: 24px; font-weight: 700; margin: 24px 0 12px; }
    h2 { font-size: 20px; font-weight: 600; margin: 20px 0 10px; }
    h3 { font-size: 16px; font-weight: 600; margin: 16px 0 8px; }
    pre { background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; }
    code { background: #f0f0f0; padding: 1px 4px; border-radius: 3px; font-size: 13px; }
    blockquote { border-left: 3px solid #ccc; margin: 0; padding-left: 16px; color: #555; }
    hr { border: none; border-top: 1px solid #e0e0e0; margin: 24px 0; }
    @media print { body { margin: 20px; } }
  </style>
</head>
<body>
  <h1>${title}</h1>
  <pre style="white-space: pre-wrap; font-family: inherit; background: none; padding: 0;">${escapeHtml(content)}</pre>
</body>
</html>`
    const w = window.open('', '_blank')
    if (!w) return
    w.document.write(html)
    w.document.close()
    w.focus()
    w.print()
  }

  const views: { id: EditorTab; label: string; onClick: () => void }[] = [
    { id: 'edit', label: '편집', onClick: () => setTab('edit') },
    { id: 'preview', label: '미리보기', onClick: () => setTab('preview') },
    {
      id: 'starmap',
      label: '성도',
      onClick: () => {
        setStarMapFilter(activeNote?.category_id ? { type: 'category', value: activeNote.category_id } : null)
        setTab('starmap')
      },
    },
  ]

  return (
    <div className="glass glass-bar flex items-center gap-4" style={{ padding: '12px 20px 12px 24px', flexWrap: 'wrap' }}>
      {/* 제목 + 기항지 + 날짜 */}
      <div className="flex flex-col min-w-0" style={{ flex: '1 1 280px' }}>
        <div className="flex items-center gap-2">
          <input
            ref={titleRef}
            value={titleValue}
            onChange={e => setTitleValue(e.target.value)}
            onBlur={handleTitleBlur}
            onKeyDown={handleTitleKeyDown}
            placeholder="제목 없음"
            aria-label="노트 제목"
            style={{
              fontFamily: 'var(--font-title)',
              fontSize: 'var(--fs-xl)',
              fontWeight: 700,
              lineHeight: 1.3,
              color: 'var(--text-primary)',
              background: 'transparent',
              border: 'none',
              outline: 'none',
              padding: 0,
              margin: 0,
              flex: 1,
              minWidth: 0,
            }}
          />
          <button
            className="sn-icon-btn"
            title={activeNote.is_favorite ? '기항지 해제' : '기항지로 지정'}
            aria-label={activeNote.is_favorite ? '기항지 해제' : '기항지로 지정'}
            aria-pressed={!!activeNote.is_favorite}
            onClick={() => toggleFavorite(activeNote.id)}
            style={{ width: 30, height: 30, fontSize: 18, color: activeNote.is_favorite ? 'var(--star)' : 'var(--text-tertiary)' }}
          >
            {activeNote.is_favorite ? '★' : '☆'}
          </button>
        </div>
        <div
          className="flex items-center gap-3"
          style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)', marginTop: '3px', fontVariantNumeric: 'tabular-nums' }}
        >
          <span>만든 날 {formatDateTime(activeNote.created_at)}</span>
          <span>고친 날 {formatDateTime(activeNote.modified_at)}</span>
        </div>
      </div>

      {/* 보기 전환 */}
      <div className="sn-segment" role="group" aria-label="보기 방식">
        {views.map(v => (
          <button key={v.id} aria-pressed={activeTab === v.id} onClick={v.onClick}>
            {v.label}
          </button>
        ))}
      </div>

      {/* 노트 동작 */}
      <div className="flex items-center gap-2">
        {routeNotice && (
          <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-tertiary)' }}>{routeNotice}</span>
        )}
        <button
          className="sn-btn"
          onClick={handleRouteAnalyze}
          disabled={routeBusy}
          title="이 노트의 키워드·태그를 분석해 같은 키워드를 가진 노트와 항로로 연결합니다"
          style={{ cursor: routeBusy ? 'wait' : undefined, opacity: routeBusy ? 0.6 : 1 }}
        >
          ⟡ 항로 분석
        </button>
        <button className="sn-btn" onClick={handlePrint}>인쇄</button>
        <button className="sn-btn is-danger" onClick={handleDelete}>삭제</button>
      </div>
    </div>
  )
}
