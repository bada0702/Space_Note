import { useEffect, useState, type ReactNode } from 'react'
import { initBackend } from '../../api/client'

/** 백엔드 준비(initBackend) 전에는 API를 호출하는 화면을 렌더하지 않는다. */
export function BackendGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<'loading' | 'ready' | Error>('loading')

  useEffect(() => {
    initBackend().then(() => setState('ready'), (e: unknown) => setState(e instanceof Error ? e : new Error(String(e))))
  }, [])

  if (state === 'ready') return <>{children}</>
  return (
    <div className="flex flex-col items-center justify-center h-screen gap-4" style={{ background: 'var(--bg-app)' }}>
      <p style={{ fontSize: '13px', color: 'var(--text-secondary)', textAlign: 'center', lineHeight: 1.6 }}>
        {state === 'loading' ? '백엔드 시작 중…' : state.message}
      </p>
    </div>
  )
}
