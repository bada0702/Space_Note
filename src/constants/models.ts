// 설정창에서 고를 수 있는 채팅 모델 목록 — 채팅은 여기서 고른 기본 모델만 사용한다.
// 백엔드 ALLOWED_CHAT_MODELS(gemini_client.py, anthropic_client.py, openai_client.py)와 맞춰야 한다.
// Ollama 모델은 설치된 목록을 받아 'ollama:<이름>' 값으로 따로 붙인다.
export const DEFAULT_MODEL = 'gemini-3.1-flash-lite'

export const MODEL_OPTIONS: { value: string; label: string; group: string }[] = [
  { value: 'gemini-3.1-flash-lite', label: 'Gemini 3.1 Flash-Lite (토큰 절약)', group: 'Google Gemini' },
  { value: 'gemini-3.5-flash-lite', label: 'Gemini 3.5 Flash-Lite', group: 'Google Gemini' },
  { value: 'gemini-3.5-flash',      label: 'Gemini 3.5 Flash',      group: 'Google Gemini' },
  { value: 'gemini-3.6-flash',      label: 'Gemini 3.6 Flash',      group: 'Google Gemini' },
  { value: 'gemini-3.7-flash',      label: 'Gemini 3.7 Flash',      group: 'Google Gemini' },
  { value: 'gemini-3.8-flash',      label: 'Gemini 3.8 Flash',      group: 'Google Gemini' },
  { value: 'gemini-4-argon',        label: 'Gemini 4 Argon',        group: 'Google Gemini' },
  { value: 'claude-haiku-4-5',      label: 'Claude Haiku 4.5',      group: 'Anthropic Claude' },
  { value: 'claude-sonnet-4-6',     label: 'Claude Sonnet 4.6',     group: 'Anthropic Claude' },
  { value: 'claude-sonnet-5-5',     label: 'Claude Sonnet 5.5',     group: 'Anthropic Claude' },
  { value: 'claude-opus-5-5',       label: 'Claude Opus 5.5',       group: 'Anthropic Claude' },
  { value: 'gpt-6-luna',            label: 'GPT-6 Luna (토큰 절약)', group: 'OpenAI GPT' },
  { value: 'gpt-6.1-sol',           label: 'GPT-6.1 Sol',           group: 'OpenAI GPT' },
  { value: 'gpt-6-astra',           label: 'GPT-6 Astra',           group: 'OpenAI GPT' },
]
