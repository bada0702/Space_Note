import { create } from 'zustand'
import type { Note, EditorTab } from '../types'
import { notesApi } from '../api/notesApi'
import { formatDateTime } from '../utils/dateFormat'

interface NotesState {
  notes: Note[]
  activeNote: Note | null
  activeTab: EditorTab
  vaultPath: string
  starMapFilter: string | null  // null = 전체, string = 카테고리 ID
  fetchNotes: (categoryId?: string) => Promise<void>
  openNote: (id: string) => Promise<void>
  saveNote: (id: string, content: string) => Promise<void>
  renameNote: (id: string, title: string) => Promise<void>
  createNote: (title: string, categoryId?: string) => Promise<Note>
  deleteNote: (id: string) => Promise<void>
  setTab: (tab: EditorTab) => void
  setStarMapFilter: (id: string | null) => void
  setVaultPath: (path: string) => void
}

export const useNotesStore = create<NotesState>((set, get) => ({
  notes: [],
  activeNote: null,
  activeTab: 'edit',
  vaultPath: '',
  starMapFilter: null,

  fetchNotes: async (categoryId) => {
    const notes = await notesApi.list(categoryId)
    set({ notes })
  },

  openNote: async (id) => {
    const note = await notesApi.get(id)
    set({ activeNote: note })
  },

  saveNote: async (id, content) => {
    const updated = await notesApi.update(id, { content })
    set(s => ({
      notes: s.notes.map(n => n.id === id ? updated : n),
      activeNote: s.activeNote?.id === id ? updated : s.activeNote,
    }))
  },

  renameNote: async (id, title) => {
    if (!title.trim()) return
    const updated = await notesApi.update(id, { title: title.trim() })
    set(s => ({
      notes: s.notes.map(n => n.id === id ? updated : n),
      activeNote: s.activeNote?.id === id ? updated : s.activeNote,
    }))
  },

  createNote: async (title, categoryId) => {
    const note = await notesApi.create(title, get().vaultPath, categoryId)
    set(s => ({ notes: [note, ...s.notes], activeNote: note }))
    return note
  },

  deleteNote: async (id) => {
    await notesApi.delete(id)
    set(s => ({
      notes: s.notes.filter(n => n.id !== id),
      activeNote: s.activeNote?.id === id ? null : s.activeNote,
    }))
  },

  setTab: (tab) => set({ activeTab: tab }),
  setStarMapFilter: (id) => set({ starMapFilter: id }),
  setVaultPath: (path) => set({ vaultPath: path }),
}))
