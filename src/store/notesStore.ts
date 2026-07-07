import { create } from 'zustand'
import type { Note, EditorTab, StarMapFilter } from '../types'
import { notesApi } from '../api/notesApi'
import { formatDateTime } from '../utils/dateFormat'

interface NotesState {
  notes: Note[]
  activeNote: Note | null
  activeTab: EditorTab
  vaultPath: string
  starMapFilter: StarMapFilter  // null = 전체, {type:'category'|'tag', value} = 필터
  archivedNotes: Note[]
  archivedCount: number
  fetchNotes: (categoryId?: string) => Promise<void>
  openNote: (id: string) => Promise<void>
  saveNote: (id: string, content: string) => Promise<void>
  renameNote: (id: string, title: string) => Promise<void>
  createNote: (title: string, categoryId?: string, content?: string) => Promise<Note>
  deleteNote: (id: string) => Promise<void>
  moveNote: (id: string, categoryId: string | null) => Promise<void>
  toggleFavorite: (id: string) => Promise<void>
  archiveNote: (id: string) => Promise<void>
  restoreNote: (id: string) => Promise<void>
  fetchArchived: () => Promise<void>
  setTab: (tab: EditorTab) => void
  setStarMapFilter: (filter: StarMapFilter) => void
  setVaultPath: (path: string) => void
}

export const useNotesStore = create<NotesState>((set, get) => ({
  notes: [],
  activeNote: null,
  activeTab: 'edit',
  vaultPath: '',
  starMapFilter: null,
  archivedNotes: [],
  archivedCount: 0,

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

  createNote: async (title, categoryId, content) => {
    const note = await notesApi.create(title, get().vaultPath, categoryId, content)
    set(s => ({ notes: [note, ...s.notes], activeNote: note }))
    return note
  },

  moveNote: async (id, categoryId) => {
    const updated = await notesApi.update(id, { category_id: categoryId })
    set(s => ({
      notes: s.notes.map(n => n.id === id ? updated : n),
      activeNote: s.activeNote?.id === id ? updated : s.activeNote,
    }))
  },

  deleteNote: async (id) => {
    await notesApi.delete(id)
    set(s => ({
      notes: s.notes.filter(n => n.id !== id),
      activeNote: s.activeNote?.id === id ? null : s.activeNote,
    }))
  },

  toggleFavorite: async (id) => {
    const note = get().notes.find(n => n.id === id) ?? get().activeNote
    if (!note) return
    const updated = await notesApi.update(id, { is_favorite: !note.is_favorite })
    set(s => ({
      notes: s.notes.map(n => n.id === id ? updated : n),
      activeNote: s.activeNote?.id === id ? updated : s.activeNote,
    }))
  },

  archiveNote: async (id) => {
    const updated = await notesApi.update(id, { is_archived: true })
    set(s => ({
      notes: s.notes.filter(n => n.id !== id),
      archivedNotes: [updated, ...s.archivedNotes],
      archivedCount: s.archivedCount + 1,
      activeNote: s.activeNote?.id === id ? null : s.activeNote,
    }))
  },

  restoreNote: async (id) => {
    const updated = await notesApi.update(id, { is_archived: false })
    set(s => ({
      notes: [updated, ...s.notes],
      archivedNotes: s.archivedNotes.filter(n => n.id !== id),
      archivedCount: Math.max(0, s.archivedCount - 1),
    }))
  },

  fetchArchived: async () => {
    const archivedNotes = await notesApi.list(undefined, true)
    set({ archivedNotes, archivedCount: archivedNotes.length })
  },

  setTab: (tab) => set({ activeTab: tab }),
  setStarMapFilter: (filter) => set({ starMapFilter: filter }),
  setVaultPath: (path) => set({ vaultPath: path }),
}))
