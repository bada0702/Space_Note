// 웹(리눅스 서버) 모드: Vite 프록시 /api + 빌드 시점 토큰
// Tauri(Windows 설치판) 모드: 실행 시 Rust가 띄운 백엔드 주소·토큰을 backend_info로 받는다
let base = '/api'
let token = import.meta.env.VITE_SPACENOTE_TOKEN ?? ''

const isTauri = () => typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

/** 현재 백엔드 주소. initBackend() 이후 값이 확정된다. */
export function apiBase(): string {
  return base
}

const BACKEND_FAIL = '백엔드를 시작하지 못했습니다. %APPDATA%\\SpaceNote\\backend.log를 확인하세요.'

/**
 * 앱 시작 시 한 번 호출. Tauri 모드면 백엔드가 응답할 때까지 기다린다.
 * 첫 실행은 백신 검사·형태소 모델 로딩으로 느릴 수 있어 프로세스가 살아 있는 동안 최대 120초 대기하고,
 * 프로세스가 죽으면 즉시 실패한다.
 */
export async function initBackend(): Promise<void> {
  if (!isTauri()) return
  const { invoke } = await import('@tauri-apps/api/core')
  const info = await invoke<{ baseUrl: string; token: string }>('backend_info')
  base = info.baseUrl
  token = info.token
  const deadline = Date.now() + 120_000
  while (Date.now() < deadline) {
    try {
      if ((await fetch(`${base}/health`)).ok) return
    } catch {
      // 백엔드 기동 중 — 재시도
    }
    if (!(await invoke<boolean>('backend_alive'))) throw new Error(BACKEND_FAIL)
    await new Promise(r => setTimeout(r, 500))
  }
  throw new Error(BACKEND_FAIL)
}

/** 모든 API 요청에 공통으로 붙는 헤더(인증 토큰 포함). */
export function authHeaders(extra?: HeadersInit): HeadersInit {
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  }
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${path}`, {
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
