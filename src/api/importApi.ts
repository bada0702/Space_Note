import { apiBase, apiFetch, authHeaders } from './client'

export interface ImportResult {
  imported: number
  skipped: { path: string; reason: string }[]
}

export const importApi = {
  /** path는 고른 폴더 기준 상대 경로 (예: 은하/노트.md) */
  files: (files: { path: string; content: string }[]) =>
    apiFetch<ImportResult>('/notes/import/files', { method: 'POST', body: JSON.stringify({ files }) }),
  /** zip은 raw body로 올린다 (백엔드에 multipart 파서가 없음) */
  zip: async (file: File): Promise<ImportResult> => {
    const res = await fetch(`${apiBase()}/notes/import/zip`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/zip' }),
      body: file,
    })
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`)
    return res.json()
  },
}
