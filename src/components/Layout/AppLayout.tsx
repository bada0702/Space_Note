import { useTheme } from './ThemeProvider'
import { useState, useEffect } from 'react'
import LiquidGlass from 'liquid-glass-react'

const SIDEBAR_WIDTH = 252
const GAP = 10  // 화면 가장자리·패널 사이 여백 — 유리 패널 뒤 배경이 보이도록
// globals.css '롤오버 Liquid Glass'의 대상 선택자와 맞춘다
const LIQUID_TARGETS = '.sn-row, .sn-cat-head, .sn-atlas-item, .sn-btn, .sn-icon-btn, .sn-segment button'

interface AppLayoutProps {
  sidebar: React.ReactNode
  main: React.ReactNode
  /** 성도 탭: 메인 영역을 유리 카드로 덮지 않고 별지도를 그대로 노출 */
  isMap: boolean
}

export function AppLayout({ sidebar, main, isMap }: AppLayoutProps) {
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

  // 롤오버 Liquid Glass: hover 중인 행·버튼에만 커서 위치(--lx/--ly)를 넣어 반사광이 따라오게 한다
  useEffect(() => {
    const handler = (e: PointerEvent) => {
      const el = (e.target as Element | null)?.closest?.<HTMLElement>(LIQUID_TARGETS)
      if (!el) return
      const r = el.getBoundingClientRect()
      el.style.setProperty('--lx', `${((e.clientX - r.left) / r.width) * 100}%`)
      el.style.setProperty('--ly', `${((e.clientY - r.top) / r.height) * 100}%`)
    }
    window.addEventListener('pointermove', handler, { passive: true })
    return () => window.removeEventListener('pointermove', handler)
  }, [])

  return (
    <div className={`sn-shell flex h-screen w-screen overflow-hidden ${isMap ? 'is-map' : ''}`} style={{ padding: GAP }}>
      {/* 유리 뒤 우주 배경 — 성도 탭에서는 별지도 캔버스가 이 위를 덮는다 */}
      <div className="sn-space" aria-hidden="true" style={{ position: 'fixed', inset: 0 }} />

      {/* 사이드바 */}
      <aside
        className="sn-glass"
        style={{
          width: sidebarOpen ? `${SIDEBAR_WIDTH}px` : '0px',
          marginRight: sidebarOpen ? GAP : 0,
          opacity: sidebarOpen ? 1 : 0,
          flexShrink: 0,
          overflow: 'hidden',
          transition: 'width 200ms ease, margin 200ms ease, opacity 200ms ease',
          position: 'relative',
          zIndex: 2,  // 성도 캔버스(메인 안의 fixed 레이어)보다 위
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
            <span style={{ fontFamily: 'var(--font-logo)', fontSize: '13px', fontWeight: 600, letterSpacing: '0.2em', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
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

      {/* 사이드바 토글 버튼 — 떠 있는 작은 알약이라 liquid-glass-react를 그대로 쓴다.
          LiquidGlass는 style의 top/left를 '중심점'으로 삼으므로(translate -50%) 크기 0인 고정 앵커에 붙인다. */}
      <div
        style={{
          position: 'fixed',
          left: sidebarOpen ? GAP + SIDEBAR_WIDTH + GAP / 2 : GAP + 4,
          top: '50%',
          zIndex: 50,
          transition: 'left 200ms ease',
        }}
      >
        <LiquidGlass
          cornerRadius={999}
          padding="0"
          displacementScale={40}
          elasticity={0.3}
          style={{ position: 'absolute', top: '0px', left: '0px' }}
        >
          <button
            onClick={() => setSidebarOpen(o => !o)}
            aria-label={sidebarOpen ? '사이드바 닫기' : '사이드바 열기'}
            title={`${sidebarOpen ? '사이드바 닫기' : '사이드바 열기'} (Ctrl+\\)`}
            style={{
              width: 18,
              height: 44,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              font: '500 14px/1 var(--font-body)',
              color: 'var(--text-secondary)',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            {sidebarOpen ? '‹' : '›'}
          </button>
        </LiquidGlass>
      </div>

      {/* 메인 편집 영역 */}
      <main
        className={`sn-main flex-1 flex flex-col overflow-hidden ${isMap ? 'is-map' : 'sn-glass'}`}
        style={{ position: 'relative', zIndex: 1, minWidth: 0 }}
      >
        {main}
      </main>
    </div>
  )
}
