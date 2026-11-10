import { create } from 'zustand'
import type { Attachment } from '../types'
import { attachmentsApi } from '../api/attachmentsApi'

interface AttachmentsState {
  items: Attachment[]
  load: (noteId: string) => Promise<void>
  addMemo: (noteId: string, name: string, text: string) => Promise<void>
  addLink: (noteId: string, url: string, name: string, description?: string) => Promise<void>
  uploadFile: (noteId: string, file: File) => Promise<void>
  remove: (id: string) => Promise<void>
  clear: () => void
}

let loadRequestId = 0

export const useAttachmentsStore = create<AttachmentsState>((set) => ({
  items: [],

  load: async (noteId) => {
    const requestId = ++loadRequestId
    const items = await attachmentsApi.list(noteId)
    if (requestId !== loadRequestId) return
    set({ items })
  },

  addMemo: async (noteId, name, text) => {
    const a = await attachmentsApi.addMemo(noteId, name, text)
    set(s => ({ items: [...s.items, a] }))
  },

  addLink: async (noteId, url, name, description) => {
    const a = await attachmentsApi.addLink(noteId, url, name, description)
    set(s => ({ items: [...s.items, a] }))
  },

  uploadFile: async (noteId, file) => {
    const a = await attachmentsApi.uploadFile(noteId, file)
    set(s => ({ items: [...s.items, a] }))
  },

  remove: async (id) => {
    await attachmentsApi.remove(id)
    set(s => ({ items: s.items.filter(i => i.id !== id) }))
  },

  clear: () => set({ items: [] }),
}))
