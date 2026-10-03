import type {
  AIModel, AIChatMessage, AISettings, ChatSource, GraphStatus, ConversationSummary, ConversationDetail,
} from '../types'
import { API_BASE, authHeaders, apiFetch } from './client'

export const aiApi = {
  getSettings: (): Promise<AISettings> =>
    apiFetch<AISettings>('/ai/settings'),
  getOllamaModels: (): Promise<{name: string}[]> =>
    apiFetch<{name: string}[]>('/ai/models/ollama'),
  patchSettings: async (data: Partial<AISettings>): Promise<void> => {
    await apiFetch('/ai/settings', { method: 'PATCH', body: JSON.stringify(data) })
  },

  // 대화 기록
  listConversations: (): Promise<ConversationSummary[]> => apiFetch('/conversations'),
  getConversation: (id: string): Promise<ConversationDetail> =>
    apiFetch(`/conversations/${encodeURIComponent(id)}`),
  saveConversation: (id: string, data: {
    model: string
    messages: { role: string; content: string; sources?: ChatSource[]; error?: string }[]
  }): Promise<ConversationSummary> =>
    apiFetch(`/conversations/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteConversation: async (id: string): Promise<void> => {
    await apiFetch(`/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
  },

  // 지식 그래프
  getGraphStatus: (): Promise<GraphStatus> => apiFetch<GraphStatus>('/graph/status'),
  rebuildGraph: (): Promise<unknown> => apiFetch('/graph/rebuild', { method: 'POST' }),
  retryFailedGraph: (): Promise<unknown> => apiFetch('/graph/retry-failed', { method: 'POST' }),

  async *streamChat(params: {
    model: AIModel
    messages: Pick<AIChatMessage, 'role' | 'content'>[]
    contextNoteId?: string
    contextCategoryId?: string
    useRag: boolean
    useWiki: boolean
  }): AsyncGenerator<{ text?: string; error?: string; sources?: ChatSource[] }> {
    const resp = await fetch(`${API_BASE}/ai/chat`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        model: params.model,
        messages: params.messages,
        context_note_id: params.contextNoteId ?? null,
        context_category_id: params.contextCategoryId ?? null,
        use_rag: params.useRag,
        use_wiki: params.useWiki,
      }),
    })
    if (!resp.ok) {
      const msg = await resp.text()
      yield { error: msg }
      return
    }
    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6)
        if (raw === '[DONE]') return
        try { yield JSON.parse(raw) } catch { /* skip */ }
      }
    }
  },
}
