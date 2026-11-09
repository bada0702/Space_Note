import { apiFetch } from './client'
import type { SearchResult, Discovery, DiscoveryRoute, Entity, RoutePath } from '../types'

// 지식 그래프 근거 필드가 없는 이전 버전 백엔드 응답도 받는다
function withEvidence<T extends { shared_concepts?: string[]; relations?: string[]; evidence?: Record<string, string> }>(d: T): T {
  return { ...d, shared_concepts: d.shared_concepts ?? [], relations: d.relations ?? [], evidence: d.evidence ?? {} }
}

export const searchApi = {
  search: (q: string, allWords = false): Promise<SearchResult[]> =>
    apiFetch<SearchResult[]>(`/search?q=${encodeURIComponent(q)}${allWords ? '&all_words=true' : ''}`),

  discoveries: (noteId?: string): Promise<Discovery[]> =>
    apiFetch<Discovery[]>(`/discoveries${noteId ? `?note_id=${noteId}` : ''}`).then(ds => ds.map(withEvidence)),

  discoveryRoutes: (): Promise<DiscoveryRoute[]> =>
    apiFetch<DiscoveryRoute[]>('/discoveries/routes')
      .then(rs => rs.map(r => ({ ...withEvidence(r), kind: r.kind ?? 'keyword' }))),

  confirmRoute: (noteA: string, noteB: string) =>
    apiFetch<{ note_a: string; note_b: string; confirmed: boolean }>('/routes', {
      method: 'POST',
      body: JSON.stringify({ note_a: noteA, note_b: noteB }),
    }),

  routePath: (from: string, to: string): Promise<RoutePath> =>
    apiFetch<RoutePath>(`/routes/path?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),

  rejectRoute: (noteA: string, noteB: string) =>
    apiFetch<{ note_a: string; note_b: string; status: string }>('/routes', {
      method: 'POST',
      body: JSON.stringify({ note_a: noteA, note_b: noteB, status: 'rejected' }),
    }),

  unconfirmRoute: (noteA: string, noteB: string) =>
    apiFetch<void>(
      `/routes?note_a=${encodeURIComponent(noteA)}&note_b=${encodeURIComponent(noteB)}`,
      { method: 'DELETE' },
    ),

  entities: (noteId: string): Promise<Entity[]> =>
    apiFetch<Entity[]>(`/entities/${noteId}`),
}
