import { useTheme } from './ThemeProvider'
import { useState, useEffect } from 'react'

const SIDEBAR_WIDTH = 252

interface AppLayoutProps {
  sidebar: React.ReactNode
  main: React.ReactNode
}

export function AppLayout({ sidebar, main }: AppLayoutProps) {
  const { theme, toggle } = useTheme()
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    return localStorage.getItem('sn-sidebar-open') !== 'false'
  })

  useEffect(() => {
    localStorage.setItem('sn-sidebar-open', String(sidebarOpen))
  }, [sidebarOpen])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === '\\') {
        e.preventDefault()
        setSidebarOpen(o => !o)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  return (
    <div className="flex h-screen w-screen overflow-hidden" style={{ background: 'var(--bg-app)' }}>
      {/* 사이드바 */}
      <aside
        className="glass glass-sidebar"
        style={{
          width: sidebarOpen ? `${SIDEBAR_WIDTH}px` : '0px',
          flexShrink: 0,
          overflow: 'hidden',
          transition: 'width 200ms ease',
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* 로고 헤더 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            height: '52px',
            padding: '0 10px 0 16px',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '9px', color: 'var(--text-primary)' }}>
            <svg width="20" height="20" viewBox="0 0 18 18" fill="none" aria-hidden="true">
              <ellipse cx="9" cy="9" rx="8" ry="4" stroke="currentColor" strokeWidth="1.1" opacity="0.55" />
              <circle cx="9" cy="9" r="1.8" fill="var(--star)" />
            </svg>
            <span style={{ fontFamily: 'var(--font-title)', fontSize: '17px', fontWeight: 700, whiteSpace: 'nowrap' }}>
              SpaceNote
            </span>
          </div>
          <button
            onClick={toggle}
            className="sn-icon-btn"
            style={{ width: 28, height: 28, fontSize: 14 }}
            title={theme === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환'}
            aria-label={theme === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환'}
          >
            {theme === 'dark' ? '☀' : '☾'}
          </button>
        </div>
        {sidebar}
      </aside>

      {/* 사이드바 토글 버튼 */}
      <button
        onClick={() => setSidebarOpen(o => !o)}
        aria-label={sidebarOpen ? '사이드바 닫기' : '사이드바 열기'}
        title={`${sidebarOpen ? '사이드바 닫기' : '사이드바 열기'} (Ctrl+\\)`}
        style={{
          position: 'fixed',
          left: sidebarOpen ? `${SIDEBAR_WIDTH - 7}px` : '0px',
          top: '50%',
          transform: 'translateY(-50%)',
          zIndex: 50,
          width: '14px',
          height: '40px',
          background: 'var(--bg-panel)',
          border: '1px solid var(--border)',
          borderRadius: '0 6px 6px 0',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '12px',
          color: 'var(--text-tertiary)',
          transition: 'left 200ms ease',
        }}
      >
        {sidebarOpen ? '‹' : '›'}
      </button>

      {/* 메인 편집 영역 */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {main}
      </main>
    </div>
  )
}
