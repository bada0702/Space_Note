import { create } from 'zustand'
import type { SearchResult, Discovery } from '../types'
import { searchApi } from '../api/searchApi'

type Panel = 'search' | 'discoveries' | null

interface SearchState {
  activePanel: Panel
  query: string
  results: SearchResult[]
  discoveries: Discovery[]
  loading: boolean

  setPanel: (p: Panel) => void
  setQuery: (q: string) => void
  doSearch: (q: string) => Promise<void>
  loadDiscoveries: (noteId?: string) => Promise<void>
}

export const useSearchStore = create<SearchState>((set) => ({
  activePanel: null,
  query: '',
  results: [],
  discoveries: [],
  loading: false,

  setPanel: (p) => set({ activePanel: p }),
  setQuery: (q) => set({ query: q }),

  doSearch: async (q) => {
    if (!q.trim()) { set({ results: [] }); return }
    set({ loading: true })
    try {
      const results = await searchApi.search(q)
      set({ results })
    } catch {
      set({ results: [] })
    } finally {
      set({ loading: false })
    }
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
