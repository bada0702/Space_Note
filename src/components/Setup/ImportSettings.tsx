import { useRef, useState } from 'react'
import { importApi, type ImportResult } from '../../api/importApi'
import { useNotesStore } from '../../store/notesStore'
import { useCategoriesStore } from '../../store/categoriesStore'

/** UTF-8로 못 읽으면 레거시 한글 문서(cp949)로 다시 읽는다. */
async function readText(file: File): Promise<string> {
  const buf = await file.arrayBuffer()
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buf).replace(/^﻿/, '')
  } catch {
    return new TextDecoder('euc-kr').decode(buf)
  }
}

/** 설정 '일반' 탭 — .md 폴더나 zip을 가져와 노트로 등록한다. */
export function ImportSettings() {
  const folderRef = useRef<HTMLInputElement>(null)
  const zipRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState('')

  const run = async (task: () => Promise<ImportResult>) => {
    setBusy(true); setError(''); setResult(null)
    try {
      setResult(await task())
      await useCategoriesStore.getState().fetchCategories()
      await useNotesStore.getState().fetchNotes()
    } catch {
      setError('가져오지 못했습니다. 파일을 확인하고 다시 시도하세요.')
    } finally {
      setBusy(false)
    }
  }

  const onFolder = (list: FileList | null) => {
    if (!list?.length) return
    const mds = Array.from(list).filter(f => f.name.toLowerCase().endsWith('.md'))
    run(async () => importApi.files(await Promise.all(mds.map(async f => ({
      // 고른 폴더 이름은 떼고, 그 안의 첫 번째 폴더가 은하가 되게 한다
      path: f.webkitRelativePath.split('/').slice(1).join('/'),
      content: await readText(f),
    })))))
  }

  const onZip = (list: FileList | null) => {
    const file = list?.[0]
    if (file) run(() => importApi.zip(file))
  }

  return (
    <div style={{ marginTop: 12, padding: 12, border: '1px solid var(--border)', borderRadius: 6 }}>
      <div className="sn-graph-head"><span>노트 가져오기</span></div>
      <p className="sn-graph-desc">
        .md 파일이 든 폴더나 zip을 가져와 노트로 등록합니다. 첫 번째 폴더 이름이 은하가 되고, 폴더 밖 파일은 미분류로 들어갑니다.
        같은 은하에 같은 제목의 노트가 있으면 건너뜁니다.
      </p>
      <div className="sn-graph-actions">
        <button type="button" className="sn-btn" disabled={busy} onClick={() => folderRef.current?.click()}>폴더 선택</button>
        <button type="button" className="sn-btn" disabled={busy} onClick={() => zipRef.current?.click()}>zip 선택</button>
      </div>
      <input
        ref={folderRef} type="file" hidden
        // React 타입 정의에 없는 비표준 속성이라 spread로 넘긴다
        {...{ webkitdirectory: '', directory: '' }}
        onChange={e => { onFolder(e.target.files); e.target.value = '' }}
      />
      <input
        ref={zipRef} type="file" hidden accept=".zip,application/zip"
        onChange={e => { onZip(e.target.files); e.target.value = '' }}
      />
      {busy && <p className="sn-graph-desc">가져오는 중...</p>}
      {result && (
        <p className="sn-graph-desc" style={{ color: 'var(--text-secondary)' }}>
          노트 {result.imported}개를 가져왔습니다{result.skipped.length > 0 && `, ${result.skipped.length}개는 건너뜀`}.
        </p>
      )}
      {result && result.skipped.length > 0 && (
        <ul className="sn-graph-desc" style={{ maxHeight: 120, overflowY: 'auto', paddingLeft: 16 }}>
          {result.skipped.map(s => <li key={s.path}>{s.path} — {s.reason}</li>)}
        </ul>
      )}
      {error && <p role="alert" className="sn-graph-error">{error}</p>}
    </div>
  )
}
