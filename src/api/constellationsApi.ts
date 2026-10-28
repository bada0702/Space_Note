import { apiFetch } from './client'
import type { ConstellationSummary, ConstellationNote } from '../types'

export const constellationsApi = {
  // 별자리 검색은 화면에서 바로 거르므로 전부 받는다 (기본 100개 제한을 넘기도록)
  list: (): Promise<ConstellationSummary[]> =>
    apiFetch<ConstellationSummary[]>('/constellations?limit=2000'),

  notes: (id: string): Promise<ConstellationNote[]> =>
    apiFetch<ConstellationNote[]>(`/constellations/${encodeURIComponent(id)}/notes`),
}
