import { useEffect, useState } from 'react'
import { useNotesStore } from '../../store/notesStore'
import { useAttachmentsStore } from '../../store/attachmentsStore'
import { attachmentsApi } from '../../api/attachmentsApi'
import type { Attachment } from '../../types'

function iconFor(a: Attachment): string {
  if (a.type === 'link') return '🔗'
  if (a.type === 'memo') return '📝'
  const m = a.mime ?? ''
  if (m === 'application/pdf') return '🌙'
  if (m.startsWith('image/')) return '🖼️'
  return '💻'
}

export function SatellitePanel() {
  const { activeNote } = useNotesStore()
  const { items, load, addMemo, addLink, uploadFile, remove, clear } = useAttachmentsStore()
  const [memoName, setMemoName] = useState('')
  const [memoText, setMemoText] = useState('')
  const [linkUrl, setLinkUrl] = useState('')
  const [linkName, setLinkName] = useState('')

  useEffect(() => {
    if (activeNote) load(activeNote.id)
    else clear()
  }, [activeNote?.id])

  if (!activeNote) return null
  const nid = activeNote.id

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) uploadFile(nid, f)
    e.target.value = ''
  }

  const onAddMemo = () => {
    if (!memoName.trim()) return
    addMemo(nid, memoName.trim(), memoText)
    setMemoName(''); setMemoText('')
  }

  const onAddLink = () => {
    if (!linkUrl.trim()) return
    addLink(nid, linkUrl.trim(), linkName.trim() || linkUrl.trim())
    setLinkUrl(''); setLinkName('')
  }

  return (
    <div className="flex flex-col h-full overflow-auto" style={{ padding: '20px 24px', gap: 16 }}>
      <h2 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
        🌙 위성 <span style={{ color: 'var(--text-secondary)', fontWeight: 400 }}>({items.length})</span>
      </h2>

      {/* 위성 목록 */}
      <ul style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {items.map(a => (
          <li key={a.id} className="flex items-center gap-2"
              style={{ fontSize: 13, color: 'var(--text-primary)', padding: '6px 8px',
                       border: '1px solid var(--border)', borderRadius: 4 }}>
            <span>{iconFor(a)}</span>
            <span className="truncate" style={{ flex: 1 }}>{a.name}</span>
            {a.type === 'file' && (
              <a href={attachmentsApi.downloadUrl(a.id)} download
                 style={{ fontSize: 11, color: 'var(--text-secondary)' }}>다운로드</a>
            )}
            {a.type === 'link' && a.url && (
              <a href={a.url} target="_blank" rel="noreferrer"
                 style={{ fontSize: 11, color: 'var(--text-secondary)' }}>열기</a>
            )}
            <button onClick={() => remove(a.id)}
                    style={{ fontSize: 11, color: 'var(--text-secondary)' }}>삭제</button>
          </li>
        ))}
        {items.length === 0 && (
          <li style={{ fontSize: 12, color: 'var(--text-secondary)' }}>아직 위성이 없습니다.</li>
        )}
      </ul>

      {/* 파일 업로드 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>파일 위성 (PDF·이미지·코드)</label>
        <input type="file" onChange={onFile} style={{ fontSize: 12 }} />
      </div>

      {/* 링크 위성 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>링크 위성</label>
        <input value={linkUrl} onChange={e => setLinkUrl(e.target.value)} placeholder="https://..."
               style={{ fontSize: 13, padding: '6px 8px', background: 'transparent',
                        border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-primary)' }} />
        <input value={linkName} onChange={e => setLinkName(e.target.value)} placeholder="제목(선택)"
               style={{ fontSize: 13, padding: '6px 8px', background: 'transparent',
                        border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-primary)' }} />
        <button onClick={onAddLink} style={{ fontSize: 12, alignSelf: 'flex-start',
                padding: '4px 12px', border: '1px solid var(--border)', borderRadius: 4,
                color: 'var(--text-primary)' }}>링크 추가</button>
      </div>

      {/* 메모 위성 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>메모 위성</label>
        <input value={memoName} onChange={e => setMemoName(e.target.value)} placeholder="메모 제목"
               style={{ fontSize: 13, padding: '6px 8px', background: 'transparent',
                        border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-primary)' }} />
        <textarea value={memoText} onChange={e => setMemoText(e.target.value)} placeholder="메모 내용" rows={3}
                  style={{ fontSize: 13, padding: '6px 8px', background: 'transparent',
                           border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-primary)' }} />
        <button onClick={onAddMemo} style={{ fontSize: 12, alignSelf: 'flex-start',
                padding: '4px 12px', border: '1px solid var(--border)', borderRadius: 4,
                color: 'var(--text-primary)' }}>메모 추가</button>
      </div>
    </div>
  )
}
