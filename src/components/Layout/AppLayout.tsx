import { useTheme } from './ThemeProvider'
import { useState, useEffect } from 'react'

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
      {/* 사이드바 — 글래스모피즘 */}
      <aside
        className="glass glass-sidebar"
        style={{
          width: sidebarOpen ? '220px' : '0px',
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
            padding: '10px 14px',
            borderBottom: '1px solid var(--glass-border)',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <ellipse cx="9" cy="9" rx="8" ry="4" stroke="currentColor" strokeWidth="1.2" />
              <circle cx="9" cy="9" r="1.5" fill="currentColor" />
            </svg>
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '0.02em', whiteSpace: 'nowrap' }}>
              SpaceNote
            </span>
          </div>
          <button
            onClick={toggle}
            style={{ fontSize: '11px', color: 'var(--text-secondary)', background: 'var(--bg-input)', padding: '2px 6px', borderRadius: '3px', border: 'none', cursor: 'pointer' }}
          >
            {theme === 'dark' ? '☀' : '●'}
          </button>
        </div>
        {sidebar}
      </aside>

      {/* 사이드바 토글 버튼 */}
      <button
        onClick={() => setSidebarOpen(o => !o)}
        aria-label={sidebarOpen ? '사이드바 닫기' : '사이드바 열기'}
        style={{
          position: 'fixed',
          left: sidebarOpen ? '214px' : '0px',
          top: '50%',
          transform: 'translateY(-50%)',
          zIndex: 50,
          width: '12px',
          height: '32px',
          background: 'var(--bg-panel)',
          border: '1px solid var(--border)',
          borderRadius: '0 3px 3px 0',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '9px',
          color: 'var(--text-secondary)',
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
