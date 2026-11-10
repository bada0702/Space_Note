import { apiBase, apiFetch, authHeaderOnly, authHeaders } from './client'
import type { Attachment } from '../types'

export interface UploadedAttachment {
  name: string
  /** 프록시(/api)를 포함한, 마크다운에 바로 넣을 수 있는 URL */
  url: string
}

const IMAGE_EXT = /\.(png|jpe?g|gif|webp|svg|bmp|avif)$/i

export function isImageFile(name: string): boolean {
  return IMAGE_EXT.test(name)
}

/** 파일을 raw body로 업로드하고 마크다운용 URL을 돌려준다. */
export async function uploadAttachment(file: File): Promise<UploadedAttachment> {
  const res = await fetch(
    `${apiBase()}/attachments?filename=${encodeURIComponent(file.name)}`,
    {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/octet-stream' }),
      body: file,
    },
  )
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`API ${res.status}: ${err}`)
  }
  const body = (await res.json()) as { name: string; url: string }
  return { name: body.name, url: `${apiBase()}${body.url}` }
}

/** 업로드 결과를 마크다운 조각으로 변환 (이미지는 ! 문법). */
export function attachmentMarkdown(a: UploadedAttachment): string {
  return isImageFile(a.name) ? `![${a.name}](${a.url})` : `[${a.name}](${a.url})`
}

/** 위성(Satellite): 노트에 종속되는 첨부 자료(파일·링크·메모) */
export const attachmentsApi = {
  list: (noteId: string) =>
    apiFetch<Attachment[]>(`/notes/${noteId}/attachments`),

  listAll: () => apiFetch<Attachment[]>('/attachments'),

  addMemo: (noteId: string, name: string, text: string) =>
    apiFetch<Attachment>(`/notes/${noteId}/attachments/memo`, {
      method: 'POST',
      body: JSON.stringify({ name, text }),
    }),

  addLink: (noteId: string, url: string, name: string, description?: string) =>
    apiFetch<Attachment>(`/notes/${noteId}/attachments/link`, {
      method: 'POST',
      body: JSON.stringify({ url, name, description }),
    }),

  uploadFile: async (noteId: string, file: File): Promise<Attachment> => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${apiBase()}/notes/${noteId}/attachments/file`, {
      method: 'POST',
      headers: authHeaderOnly(),
      body: form,
    })
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`)
    return res.json()
  },

  downloadUrl: (id: string) => `${apiBase()}/attachments/${id}/download`,

  remove: (id: string) =>
    apiFetch<void>(`/attachments/${id}`, { method: 'DELETE' }),
}
