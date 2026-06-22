import { apiFetch } from './client'
import type { SearchResult, Discovery, Entity } from '../types'

export const searchApi = {
  search: (q: string): Promise<SearchResult[]> =>
    apiFetch<SearchResult[]>(`/search?q=${encodeURIComponent(q)}`),

  discoveries: (noteId?: string): Promise<Discovery[]> =>
    apiFetch<Discovery[]>(`/discoveries${noteId ? `?note_id=${noteId}` : ''}`),

  entities: (noteId: string): Promise<Entity[]> =>
    apiFetch<Entity[]>(`/entities/${noteId}`),
}
