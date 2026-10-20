import { apiFetch } from './client'
import type { ConstellationSummary, ConstellationNote } from '../types'

export const constellationsApi = {
  list: (): Promise<ConstellationSummary[]> =>
    apiFetch<ConstellationSummary[]>('/constellations'),

  notes: (id: string): Promise<ConstellationNote[]> =>
    apiFetch<ConstellationNote[]>(`/constellations/${encodeURIComponent(id)}/notes`),
}
