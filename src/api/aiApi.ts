import type { AIModel, AIChatMessage, AISettings } from '../types'

const BASE = 'http://localhost:8001'

export const aiApi = {
  getSettings: (): Promise<AISettings> =>
    fetch(`${BASE}/ai/settings`).then(r => r.json()),

  patchSettings: (data: Partial<AISettings>): Promise<void> =>
    fetch(`${BASE}/ai/settings`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }).then(() => {}),

  async *streamChat(params: {
    model: AIModel
    messages: Pick<AIChatMessage, 'role' | 'content'>[]
    contextNoteId?: string
    contextCategoryId?: string
    useRag: boolean
    useWiki: boolean
  }): AsyncGenerator<{ text?: string; error?: string }> {
    const resp = await fetch(`${BASE}/ai/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
