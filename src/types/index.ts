export interface Category {
  id: string
  name: string
  color: string
  sort_order: number
  created_at: string
}

export interface Note {
  id: string
  path: string
  title: string
  content: string
  category_id: string | null
  tags: string[]
  word_count: number
  analysis_status: 'pending' | 'analyzed' | 'failed'
  is_favorite: boolean
  is_archived: boolean
  created_at: string
  modified_at: string
}

export type EditorTab = 'edit' | 'preview' | 'starmap'
export type Theme = 'dark' | 'light'

export type AIModel =
  | 'claude-sonnet-4-6'
  | 'claude-haiku-4-5'
  | 'gemini-3.5-flash'
  | 'gemini-3.6-flash'
  | 'gemini-3.7-flash'
  | 'gemini-3.8-flash'
  | 'gemini-2.5-flash'
  | (string & {})

export interface AIChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
  error?: string
}

export interface ChatContext {
  noteId?: string
  categoryId?: string
  useRag: boolean
  useWiki: boolean
}

export interface AISettings {
  anthropic_api_key: string
  openai_api_key: string
  google_api_key: string
  default_model: string
  vault_dir?: string
}

export interface SearchResult {
  id: string
  title: string
  content_preview: string
  category_id: string | null
  created_at: string
  modified_at: string
}

export interface Discovery {
  note_id: string
  title: string
  category_id: string | null
  shared_count: number
  shared_entities: string[]
  modified_at: string
}

export interface DiscoveryRoute {
  note_a: string
  note_b: string
  shared_entities: string[]
  confirmed: boolean
}

export interface Entity {
  id: string
  note_id: string
  name: string
  type: string
  created_at: string
}

export interface TagSummary {
  tag: string
  count: number
}

export interface TaggedNote {
  id: string
  title: string
  category_id: string | null
  modified_at: string
}

export type StarMapFilter = { type: 'category' | 'tag'; value: string } | null
