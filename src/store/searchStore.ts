import { create } from 'zustand'
import type { SearchResult, Discovery } from '../types'
import { searchApi } from '../api/searchApi'

type Panel = 'search' | 'discoveries' | 'tags' | null
type SortBy = 'created' | 'title'
type SortDir = 'asc' | 'desc'

function sortResults(results: SearchResult[], sortBy: SortBy, sortDir: SortDir) {
  const sorted = [...results].sort((a, b) =>
    sortBy === 'title'
      ? a.title.localeCompare(b.title, 'ko')
      : a.created_at.localeCompare(b.created_at)
  )
  return sortDir === 'asc' ? sorted : sorted.reverse()
}

interface SearchState {
  activePanel: Panel
  query: string
  results: SearchResult[]
  sortBy: SortBy
  sortDir: SortDir
  discoveries: Discovery[]
  loading: boolean

  setPanel: (p: Panel) => void
  setQuery: (q: string) => void
  doSearch: (q: string) => Promise<void>
  setSort: (by: SortBy) => void
  loadDiscoveries: (noteId?: string) => Promise<void>
}

export const useSearchStore = create<SearchState>((set, get) => ({
  activePanel: null,
  query: '',
  results: [],
  sortBy: 'created',
  sortDir: 'desc',
  discoveries: [],
  loading: false,

  setPanel: (p) => set({ activePanel: p }),
  setQuery: (q) => set({ query: q }),

  doSearch: async (q) => {
    if (!q.trim()) { set({ results: [] }); return }
    set({ loading: true })
    try {
      const { sortBy, sortDir } = get()
      const results = await searchApi.search(q)
      set({ results: sortResults(results, sortBy, sortDir) })
    } catch {
      set({ results: [] })
    } finally {
      set({ loading: false })
    }
  },

  setSort: (by) => {
    const { sortBy, sortDir, results } = get()
    const nextDir: SortDir =
      by === sortBy ? (sortDir === 'asc' ? 'desc' : 'asc') : by === 'title' ? 'asc' : 'desc'
    set({ sortBy: by, sortDir: nextDir, results: sortResults(results, by, nextDir) })
  },

  loadDiscoveries: async (noteId) => {
    set({ loading: true })
    try {
      const discoveries = await searchApi.discoveries(noteId)
      set({ discoveries })
    } catch {
      set({ discoveries: [] })
    } finally {
      set({ loading: false })
    }
  },
}))
