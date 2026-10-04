import { create } from 'zustand'
import type { AIModel, AIChatMessage, ChatContext, AISettings, ConversationSummary } from '../types'
import { aiApi } from '../api/aiApi'
import { DEFAULT_MODEL } from '../constants/models'

// crypto.randomUUID는 보안 컨텍스트(HTTPS/localhost)에서만 존재 → HTTP로 IP/DDNS 접속 시 대체 id
const newId = () =>
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`

function cleanGeminiGrounding(text: string): string {
  if (!text) return text
  let cleaned = text.replace(/[\ue200][a-zA-Z0-9]+[\ue202][^\ue201]*[\ue201]/g, '')
  cleaned = cleaned.replace(/[\ue200-\ue207]/g, '')
  return cleaned
}

interface AIState {
  messages: AIChatMessage[]
  conversationId: string
  conversations: ConversationSummary[]
  model: AIModel
  context: ChatContext
  streaming: boolean
  settings: AISettings | null
  panelOpen: boolean
  showSettings: boolean

  setContext: (c: Partial<ChatContext>) => void
  setPanelOpen: (v: boolean) => void
  setShowSettings: (v: boolean) => void
  loadSettings: () => Promise<void>
  saveSettings: (data: Partial<AISettings>) => Promise<void>
  sendMessage: (text: string) => Promise<void>
  clearMessages: () => void
  loadConversations: () => Promise<void>
  openConversation: (id: string) => Promise<void>
  deleteConversation: (id: string) => Promise<void>
}

export const useAIStore = create<AIState>((set, get) => ({
  messages: [],
  conversationId: newId(),
  conversations: [],
  model: DEFAULT_MODEL,
  context: { useRag: true, useWiki: false },
  streaming: false,
  settings: null,
  panelOpen: false,
  showSettings: false,

  setContext: (c) => set(s => ({ context: { ...s.context, ...c } })),
  setPanelOpen: (v) => set({ panelOpen: v }),
  setShowSettings: (v) => set({ showSettings: v }),
  // "새 대화": 화면을 비우고 새 id로 시작 (이전 대화는 이미 저장되어 있다)
  clearMessages: () => {
    if (get().streaming) return
    set({ messages: [], conversationId: newId() })
  },

  loadConversations: async () => {
    try {
      set({ conversations: await aiApi.listConversations() })
    } catch (e) {
      console.error('대화 목록 조회 실패:', e)
    }
  },

  openConversation: async (id) => {
    if (get().streaming) return
    const conv = await aiApi.getConversation(id)
    set({
      conversationId: conv.id,
      messages: conv.messages.map(m => ({
        id: newId(), role: m.role, content: m.content,
        sources: m.sources, error: m.error ?? undefined,
      })),
    })
  },

  deleteConversation: async (id) => {
    await aiApi.deleteConversation(id)
    if (get().conversationId === id) get().clearMessages()
    await get().loadConversations()
  },

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
    const { model, context, messages, conversationId } = get()

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
        if (chunk.sources) {
          const sources = chunk.sources
          set(s => ({
            messages: s.messages.map(m => (m.id === assistantMsg.id ? { ...m, sources } : m)),
          }))
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
      if (!accumulated) {
        set(s => ({
          messages: s.messages.map(m =>
            m.id === assistantMsg.id && !m.error
              ? { ...m, content: '오류: 모델이 빈 응답을 반환했습니다', error: 'empty' }
              : m
          ),
        }))
      }
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e)
      set(s => ({
        messages: s.messages.map(m =>
          m.id === assistantMsg.id ? { ...m, content: `오류: ${error}`, error } : m
        ),
      }))
    } finally {
      set(s => ({
        messages: s.messages.map(m =>
          m.id === assistantMsg.id ? { ...m, isStreaming: false } : m
        ),
        streaming: false,
      }))
      // 답변이든 오류든 한 번 주고받을 때마다 대화 전체를 저장 (다른 대화로 옮겨갔어도 이 대화 id로)
      const saved = get().conversationId === conversationId ? get().messages : null
      if (saved) {
        try {
          await aiApi.saveConversation(conversationId, {
            model,
            messages: saved.map(m => ({
              role: m.role, content: m.content,
              ...(m.sources ? { sources: m.sources } : {}),
              ...(m.error ? { error: m.error } : {}),
            })),
          })
          await get().loadConversations()
        } catch (e) {
          console.error('대화 저장 실패:', e)
        }
      }
    }
  },
}))
