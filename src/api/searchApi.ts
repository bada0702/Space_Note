import { apiFetch } from './client'
import type { SearchResult, Discovery, DiscoveryRoute, Entity } from '../types'

export const searchApi = {
  search: (q: string): Promise<SearchResult[]> =>
    apiFetch<SearchResult[]>(`/search?q=${encodeURIComponent(q)}`),

  discoveries: (noteId?: string): Promise<Discovery[]> =>
    apiFetch<Discovery[]>(`/discoveries${noteId ? `?note_id=${noteId}` : ''}`),

  discoveryRoutes: (): Promise<DiscoveryRoute[]> =>
    apiFetch<DiscoveryRoute[]>('/discoveries/routes'),

  confirmRoute: (noteA: string, noteB: string) =>
    apiFetch<{ note_a: string; note_b: string; confirmed: boolean }>('/routes', {
      method: 'POST',
      body: JSON.stringify({ note_a: noteA, note_b: noteB }),
    }),

  unconfirmRoute: (noteA: string, noteB: string) =>
    apiFetch<void>(
      `/routes?note_a=${encodeURIComponent(noteA)}&note_b=${encodeURIComponent(noteB)}`,
      { method: 'DELETE' },
    ),

  entities: (noteId: string): Promise<Entity[]> =>
    apiFetch<Entity[]>(`/entities/${noteId}`),
}
