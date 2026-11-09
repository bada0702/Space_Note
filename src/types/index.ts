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
  graph_status?: 'idle' | 'pending' | 'done' | 'failed'
  graph_error?: string | null
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
  | 'gemini-3.1-flash-lite'
  | 'gemini-3.5-flash-lite'
  | 'gemini-3.5-flash'
  | 'gemini-3.6-flash'
  | 'gemini-3.7-flash'
  | 'gemini-3.8-flash'
  | 'gemini-2.5-flash'
  | 'gemini-4-argon'
  | 'claude-sonnet-5-5'
  | 'claude-opus-5-5'
  | 'gpt-6-luna'
  | 'gpt-6.1-sol'
  | 'gpt-6-astra'
  | (string & {})

/** RAG 답변의 근거 노트 — path는 노트를 고른 이유(지식 그래프 관계 경로 또는 키워드 일치). */
export interface ChatSource {
  id: string
  title: string
  path: string
}

export interface AIChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
  error?: string
  sources?: ChatSource[]
}

/** 저장된 AI 대화 목록 항목 */
export interface ConversationSummary {
  id: string
  title: string
  model: string
  created_at: string
  updated_at: string
}

export interface ConversationDetail extends ConversationSummary {
  messages: { role: 'user' | 'assistant'; content: string; sources: ChatSource[]; error: string | null }[]
}

export interface GraphStatus {
  idle: number
  pending: number
  done: number
  failed: number
  total: number
  concepts: number
  relations: number
  failures?: { id: string; title: string; error: string | null }[]
  rate_per_minute: number
  eta_minutes: number
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
  graph_model?: string            // 지식 그래프(온톨로지) 추출 모델 — gemini-* 또는 ollama:<이름>
  ollama_base_url?: string
  ollama_custom_models?: string[] // 설치 목록에 없어도 직접 추가한 Ollama 모델 이름
  app_title?: string              // 왼쪽 위 앱 이름 — 비어 있으면 'SpaceNote'
  app_logo?: string               // 왼쪽 위 로고 이미지(data URL) — 비어 있으면 기본 로고
}

/** 외부 에이전트(aibot 등)용 MCP 서버 설정 */
export interface McpConfig {
  enabled: boolean
  allow_write: boolean
  token: string
  url: string
  tools: string[]
  client_config: { mcpServers: Record<string, { url: string; headers: Record<string, string> }> } | null
  aibot_config: string
  aibot_registered: boolean
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
  shared_concepts: string[]
  relations: string[]
  evidence: Record<string, string>
  modified_at: string
}

export interface DiscoveryRoute {
  note_a: string
  note_b: string
  shared_entities: string[]
  shared_concepts: string[]
  relations: string[]
  evidence: Record<string, string>
  kind: 'relation' | 'concept' | 'keyword' | 'none'
  confirmed: boolean
}

export interface Entity {
  id: string
  note_id: string
  name: string
  type: string
  created_at: string
}

/** 별자리: 여러 노트(은하)에 걸친 지식 그래프 개념 */
export interface ConstellationSummary {
  id: string
  name: string
  type: string
  note_count: number
  galaxy_count: number
}

export interface ConstellationNote {
  id: string
  title: string
  category_id: string | null
  modified_at: string
}

export type StarMapFilter =
  | { type: 'category'; value: string }
  | { type: 'constellation'; value: string; label: string } // value = 개념 id
  | null

export interface ConstellationGraphNode {
  id: string
  name: string
  type: string
}

export interface ConstellationGraphEdge {
  source: string
  pred: string
  target: string
  evidence: string | null
  notes: { id: string; title: string }[]
}

export interface ConstellationGraph {
  center: ConstellationGraphNode
  nodes: ConstellationGraphNode[]
  edges: ConstellationGraphEdge[]
}

export type RoutePathNode =
  | { kind: 'note'; id: string; title: string }
  | { kind: 'concept'; id: string; name: string }

export type RoutePathEdge =
  | { kind: 'contains' }
  | { kind: 'relation'; pred: string; subject: string; object: string; evidence: string | null }

export interface RoutePath {
  found: boolean
  nodes: RoutePathNode[]
  edges: RoutePathEdge[]
}

/** 일괄 키워드 분석(AI·파이썬) 진행 수 — 서버 메모리 기준이라 재시작하면 초기화된다 */
export interface AnalyzeProgress {
  kind: 'ai' | 'python' | null
  total: number
  done: number
  failed: number
  started_at: string | null
  running: boolean
}
