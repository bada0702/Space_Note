import { create } from 'zustand'
import type { AIModel, AIChatMessage, ChatContext, AISettings } from '../types'
import { aiApi } from '../api/aiApi'

const newId = () => crypto.randomUUID()

function cleanGeminiGrounding(text: string): string {
  if (!text) return text
  let cleaned = text.replace(/[\ue200][a-zA-Z0-9]+[\ue202][^\ue201]*[\ue201]/g, '')
  cleaned = cleaned.replace(/[\ue200-\ue207]/g, '')
  return cleaned
}

interface AIState {
  messages: AIChatMessage[]
  model: AIModel
  context: ChatContext
  streaming: boolean
  settings: AISettings | null
  panelOpen: boolean
  showSettings: boolean

  setModel: (m: AIModel) => void
  setContext: (c: Partial<ChatContext>) => void
  setPanelOpen: (v: boolean) => void
  setShowSettings: (v: boolean) => void
  loadSettings: () => Promise<void>
  saveSettings: (data: Partial<AISettings>) => Promise<void>
  sendMessage: (text: string) => Promise<void>
  clearMessages: () => void
}

export const useAIStore = create<AIState>((set, get) => ({
  messages: [],
  model: 'claude-sonnet-4-6',
  context: { useRag: true, useWiki: false },
  streaming: false,
  settings: null,
  panelOpen: false,
  showSettings: false,

  setModel: (model) => set({ model }),
  setContext: (c) => set(s => ({ context: { ...s.context, ...c } })),
  setPanelOpen: (v) => set({ panelOpen: v }),
  setShowSettings: (v) => set({ showSettings: v }),
  clearMessages: () => set({ messages: [] }),

  loadSettings: async () => {
    try {
      const settings = await aiApi.getSettings()
      set({ settings })
      if (settings.default_model) {
        set({ model: settings.default_model as AIModel })
      }
    } catch {
      // 백엔드 미실행 시 무시
    }
  },

  saveSettings: async (data) => {
    await aiApi.patchSettings(data)
    await get().loadSettings()
  },

  sendMessage: async (text) => {
    if (get().streaming) return
    const { model, context, messages } = get()

    const userMsg: AIChatMessage = { id: newId(), role: 'user', content: text }
    const assistantMsg: AIChatMessage = {
      id: newId(), role: 'assistant', content: '', isStreaming: true,
    }

    set(s => ({ messages: [...s.messages, userMsg, assistantMsg], streaming: true }))

    const history = [...messages, userMsg].map(m => ({ role: m.role, content: m.content }))
    let accumulated = ''

    try {
      for await (const chunk of aiApi.streamChat({
        model,
        messages: history,
        contextNoteId: context.noteId,
        contextCategoryId: context.categoryId,
        useRag: context.useRag,
        useWiki: context.useWiki,
      })) {
        if (chunk.error) {
          set(s => ({
            messages: s.messages.map(m =>
              m.id === assistantMsg.id
                ? { ...m, content: `오류: ${chunk.error}`, isStreaming: false, error: chunk.error }
                : m
            ),
          }))
          return
        }
        if (chunk.text) {
          accumulated += chunk.text
          set(s => ({
            messages: s.messages.map(m =>
              m.id === assistantMsg.id ? { ...m, content: cleanGeminiGrounding(accumulated) } : m
            ),
          }))
        }
      }
    } finally {
      set(s => ({
        messages: s.messages.map(m =>
          m.id === assistantMsg.id ? { ...m, isStreaming: false } : m
        ),
        streaming: false,
      }))
    }
  },
}))
