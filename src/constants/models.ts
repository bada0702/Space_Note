// 설정창에서 고를 수 있는 채팅 모델 목록 — 채팅은 여기서 고른 기본 모델만 사용한다.
// 백엔드 ALLOWED_CHAT_MODELS(gemini_client.py, anthropic_client.py)와 맞춰야 한다.
export const DEFAULT_MODEL = 'gemini-3.1-flash-lite'

export const MODEL_OPTIONS: { value: string; label: string; group: string }[] = [
  { value: 'gemini-3.1-flash-lite', label: 'Gemini 3.1 Flash-Lite (토큰 절약)', group: 'Google Gemini' },
  { value: 'gemini-3.5-flash-lite', label: 'Gemini 3.5 Flash-Lite', group: 'Google Gemini' },
  { value: 'gemini-3.5-flash',      label: 'Gemini 3.5 Flash',      group: 'Google Gemini' },
  { value: 'gemini-3.6-flash',      label: 'Gemini 3.6 Flash',      group: 'Google Gemini' },
  { value: 'gemini-3.7-flash',      label: 'Gemini 3.7 Flash',      group: 'Google Gemini' },
  { value: 'gemini-3.8-flash',      label: 'Gemini 3.8 Flash',      group: 'Google Gemini' },
  { value: 'claude-haiku-4-5',      label: 'Claude Haiku 4.5',      group: 'Anthropic Claude' },
  { value: 'claude-sonnet-4-6',     label: 'Claude Sonnet 4.6',     group: 'Anthropic Claude' },
]
