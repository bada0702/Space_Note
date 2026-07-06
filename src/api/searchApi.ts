import { apiFetch } from './client'
import type { SearchResult, Discovery, DiscoveryRoute, Entity } from '../types'

export const searchApi = {
  search: (q: string): Promise<SearchResult[]> =>
    apiFetch<SearchResult[]>(`/search?q=${encodeURIComponent(q)}`),

  discoveries: (noteId?: string): Promise<Discovery[]> =>
    apiFetch<Discovery[]>(`/discoveries${noteId ? `?note_id=${noteId}` : ''}`),

  discoveryRoutes: (): Promise<DiscoveryRoute[]> =>
    apiFetch<DiscoveryRoute[]>('/discoveries/routes'),

  entities: (noteId: string): Promise<Entity[]> =>
    apiFetch<Entity[]>(`/entities/${noteId}`),
}
