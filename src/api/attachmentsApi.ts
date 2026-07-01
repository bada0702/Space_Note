import { apiFetch, API_BASE, authHeaderOnly } from './client'
import type { Attachment } from '../types'

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
    const res = await fetch(`${API_BASE}/notes/${noteId}/attachments/file`, {
      method: 'POST',
      headers: authHeaderOnly(),
      body: form,
    })
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`)
    return res.json()
  },

  downloadUrl: (id: string) => `${API_BASE}/attachments/${id}/download`,

  remove: (id: string) =>
    apiFetch<void>(`/attachments/${id}`, { method: 'DELETE' }),
}
