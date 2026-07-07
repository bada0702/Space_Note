import { apiFetch } from './client'
import type { Note } from '../types'

export const notesApi = {
  list: (categoryId?: string, archived?: boolean) => {
    const params = new URLSearchParams()
    if (categoryId) params.set('category_id', categoryId)
    if (archived) params.set('archived', 'true')
    const qs = params.toString()
    return apiFetch<Note[]>(`/notes${qs ? `?${qs}` : ''}`)
  },
  get: (id: string) => apiFetch<Note>(`/notes/${id}`),
  create: (title: string, vaultPath: string, categoryId?: string, content?: string) =>
    apiFetch<Note>('/notes', {
      method: 'POST',
      body: JSON.stringify({ title, vault_path: vaultPath, category_id: categoryId, content }),
    }),
  update: (id: string, patch: {
    title?: string; content?: string; category_id?: string | null
    tags?: string[]; is_favorite?: boolean; is_archived?: boolean
  }) =>
    apiFetch<Note>(`/notes/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  delete: (id: string) => apiFetch<void>(`/notes/${id}`, { method: 'DELETE' }),
  analyzeAll: () =>
    apiFetch<{ queued: number }>('/notes/analyze', { method: 'POST' }),
  analyzeOne: (id: string) =>
    apiFetch<{ queued: number }>(`/notes/${id}/analyze`, { method: 'POST' }),
}
