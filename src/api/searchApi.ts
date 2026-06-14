import type { SearchResult, Discovery, Entity } from '../types'

const BASE = 'http://localhost:8001'

export const searchApi = {
  search: (q: string): Promise<SearchResult[]> =>
    fetch(`${BASE}/search?q=${encodeURIComponent(q)}`).then(r => r.json()),

  discoveries: (noteId?: string): Promise<Discovery[]> =>
    fetch(`${BASE}/discoveries${noteId ? `?note_id=${noteId}` : ''}`).then(r => r.json()),

  entities: (noteId: string): Promise<Entity[]> =>
    fetch(`${BASE}/entities/${noteId}`).then(r => r.json()),
}
