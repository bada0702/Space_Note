import { useState } from 'react'
import { resetApi, RESET_CONFIRM_TEXT, type ResetPreview } from '../../api/resetApi'
import { useNotesStore } from '../../store/notesStore'
import { useCategoriesStore } from '../../store/categoriesStore'
import { useAIStore } from '../../store/aiStore'

/** 설정 '일반' 탭의 위험 구역 — 설정만 남기고 노트·은하·분석 데이터·채팅 기록과 vault의 노트 파일을 지운다. */
export function ResetSettings({ onDone }: { onDone: () => void }) {
  const [preview, setPreview] = useState<ResetPreview | null>(null)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const open = async () => {
    setError('')
    try { setPreview(await resetApi.preview()) }
    catch { setError('초기화 대상을 불러오지 못했습니다. 백엔드가 실행 중인지 확인하세요.') }
  }

  const cancel = () => { setPreview(null); setTyped('') }

  const run = async () => {
    setBusy(true)
    try {
      await resetApi.reset()
      // 지워진 데이터를 화면에서도 비운다
      useNotesStore.setState({ activeNote: null, starMapFilter: null, archivedNotes: [], archivedCount: 0 })
      await useNotesStore.getState().fetchNotes()
      await useCategoriesStore.getState().fetchCategories()
      useAIStore.getState().clearMessages()
      await useAIStore.getState().loadConversations()
      onDone()
    } catch {
      setError('초기화하지 못했습니다. 잠시 후 다시 시도하세요.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ marginTop: 12, padding: 12, border: '1px solid var(--danger)', borderRadius: 6 }}>
      <div className="sn-graph-head"><span style={{ color: 'var(--danger)' }}>위험 구역</span></div>
      <p className="sn-graph-desc">
        API 키 등 설정만 남기고 노트·은하·항로·지식 그래프·AI 채팅 기록과 노트 파일(.md, 첨부파일)을 모두 지웁니다. 되돌릴 수 없습니다.
      </p>

      {!preview && (
        <div className="sn-graph-actions">
          <button type="button" className="sn-btn is-danger" onClick={open}>노트 초기화</button>
        </div>
      )}

      {preview && (
        <>
          <p className="sn-graph-desc" style={{ color: 'var(--text-secondary)' }}>
            노트 {preview.notes}개, 은하 {preview.categories}개, 채팅 {preview.conversations}개,
            파일 {preview.files}개({preview.vault_dir})가 삭제됩니다.
            계속하려면 아래에 <b>{RESET_CONFIRM_TEXT}</b>를 입력하세요.
          </p>
          <input
            aria-label="초기화 확인 문구"
            value={typed}
            onChange={e => setTyped(e.target.value)}
            placeholder={RESET_CONFIRM_TEXT}
            style={{
              marginTop: 8, width: '100%', padding: '6px 10px', borderRadius: 5, boxSizing: 'border-box',
              background: 'var(--bg-input)', color: 'var(--text-primary)', border: '1px solid var(--border)',
              fontSize: 13, outline: 'none',
            }}
          />
          <div className="sn-graph-actions">
            <button
              type="button"
              className="sn-btn is-danger"
              disabled={busy || typed !== RESET_CONFIRM_TEXT}
              onClick={run}
              style={typed === RESET_CONFIRM_TEXT ? { color: 'var(--danger)', borderColor: 'var(--danger)' } : undefined}
            >
              {busy ? '초기화 중...' : '초기화 실행'}
            </button>
            <button type="button" className="sn-btn" disabled={busy} onClick={cancel}>취소</button>
          </div>
        </>
      )}
      {error && <p role="alert" className="sn-graph-error">{error}</p>}
    </div>
  )
}
