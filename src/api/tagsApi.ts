import { apiFetch } from './client'
import type { TagSummary, TaggedNote } from '../types'

export const tagsApi = {
  list: (): Promise<TagSummary[]> =>
    apiFetch<TagSummary[]>('/tags'),

  notesForTag: (tag: string): Promise<TaggedNote[]> =>
    apiFetch<TaggedNote[]>(`/tags/${encodeURIComponent(tag)}/notes`),
}
