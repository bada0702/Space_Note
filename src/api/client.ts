export const API_BASE = '/api'
const TOKEN = import.meta.env.VITE_SPACENOTE_TOKEN ?? ''

/** 모든 API 요청에 공통으로 붙는 헤더(인증 토큰 포함). */
export function authHeaders(extra?: HeadersInit): HeadersInit {
  return {
    'Content-Type': 'application/json',
    ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
    ...extra,
  }
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: authHeaders(options?.headers),
    ...options,
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`API ${res.status}: ${err}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}
