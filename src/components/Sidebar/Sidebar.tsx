import { useEffect, useRef, useState } from 'react'
import { VoyageLog } from './VoyageLog'
import { useNotesStore } from '../../store/notesStore'
import { useAIStore } from '../../store/aiStore'
import { useSearchStore } from '../../store/searchStore'

export function Sidebar() {
  const { setTab, setStarMapFilter, activeTab, starMapFilter, notes, openNote } = useNotesStore()
  const { panelOpen, setPanelOpen, showSettings, setShowSettings } = useAIStore()
  const { activePanel, setPanel, query, setQuery, doSearch } = useSearchStore()
  const searchRef = useRef<HTMLInputElement>(null)
  const [searchFocused, setSearchFocused] = useState(false)
  const [highlight, setHighlight] = useState(-1)

  // Ctrl/Cmd+K → 사이드바 검색창 포커스
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        searchRef.current?.focus()
        searchRef.current?.select()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // 각 버튼 클릭 시 나머지 패널을 모두 닫고 해당 항목만 활성화
  const closeAll = () => {
    setPanelOpen(false)
    setPanel(null)
    setShowSettings(false)
  }

  const handleStarMap = () => {
    closeAll()
    setStarMapFilter(null)
    setTab('starmap')
  }

  const handleNavPanel = (id: 'discoveries' | 'search' | 'constellations') => {
    const isAlreadyOpen = activePanel === id && !panelOpen && !showSettings
    closeAll()
    if (!isAlreadyOpen) setPanel(id)
  }

  const handleAIChat = () => {
    const isAlreadyOpen = panelOpen && !showSettings
    closeAll()
    if (!isAlreadyOpen) setPanelOpen(true)
  }

  // 입력 중 제목이 일치하는 노트 바로가기 (최대 6개)
  const q = query.trim().toLowerCase()
  const titleMatches = q ? notes.filter(n => n.title.toLowerCase().includes(q)).slice(0, 6) : []
  const showSuggestions = searchFocused && titleMatches.length > 0

  const openFullSearch = () => {
    if (!query.trim()) return
    closeAll()
    setPanel('search')
    doSearch(query)
    searchRef.current?.blur()
  }

  const jumpToNote = (id: string) => {
    closeAll()
    openNote(id)
    setTab('edit')
    setQuery('')
    searchRef.current?.blur()
  }

  const handleSearchKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' && titleMatches.length) {
      e.preventDefault()
      setHighlight(h => (h + 1) % titleMatches.length)
    } else if (e.key === 'ArrowUp' && titleMatches.length) {
      e.preventDefault()
      setHighlight(h => (h <= 0 ? titleMatches.length - 1 : h - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (highlight >= 0 && titleMatches[highlight]) jumpToNote(titleMatches[highlight].id)
      else openFullSearch()
    } else if (e.key === 'Escape') {
      setQuery('')
      searchRef.current?.blur()
    }
  }

  // 활성 상태: 다른 패널이 열려 있으면 해당 항목은 비활성
  const isStarMapActive = activeTab === 'starmap' && starMapFilter === null && !panelOpen && !activePanel && !showSettings

  const navItems = [
    { key: 'starmap', icon: '✦', label: '성도', active: isStarMapActive, onClick: handleStarMap },
    { key: 'search', icon: '⌕', label: '항법', active: activePanel === 'search' && !panelOpen && !showSettings, onClick: () => handleNavPanel('search') },
    { key: 'discoveries', icon: '⟡', label: '미개척 항로', active: activePanel === 'discoveries' && !panelOpen && !showSettings, onClick: () => handleNavPanel('discoveries') },
    { key: 'constellations', icon: '✧', label: '별자리', active: activePanel === 'constellations' && !panelOpen && !showSettings, onClick: () => handleNavPanel('constellations') },
    { key: 'ai', icon: '◈', label: 'AI 채팅', active: panelOpen && !showSettings, onClick: handleAIChat },
  ]

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* 노트 검색 */}
      <div style={{ position: 'relative', padding: '0 12px 10px', flexShrink: 0 }}>
        <div className="sn-search">
          <span aria-hidden="true" className="sn-search-icon">⌕</span>
          <input
            ref={searchRef}
            type="search"
            value={query}
            onChange={e => { setQuery(e.target.value); setHighlight(-1) }}
            onKeyDown={handleSearchKey}
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setTimeout(() => setSearchFocused(false), 120)}
            placeholder="노트 검색"
            aria-label="노트 검색"
            role="combobox"
            aria-expanded={showSuggestions}
            aria-controls="sn-search-suggest"
          />
          {!searchFocused && !query && <kbd className="sn-kbd">Ctrl K</kbd>}
        </div>
        {showSuggestions && (
          <div id="sn-search-suggest" role="listbox" className="sn-suggest">
            {titleMatches.map((n, i) => (
              <button
                key={n.id}
                role="option"
                aria-selected={i === highlight}
                className="sn-row"
                onMouseDown={e => e.preventDefault()}
                onClick={() => jumpToNote(n.id)}
                onMouseEnter={() => setHighlight(i)}
              >
                <span className="sn-row-text">{n.title}</span>
              </button>
            ))}
            <button
              className="sn-row sn-suggest-all"
              onMouseDown={e => e.preventDefault()}
              onClick={openFullSearch}
            >
              <span className="sn-row-text">‘{query.trim()}’ 본문까지 검색 (Enter)</span>
            </button>
          </div>
        )}
      </div>

      {/* 주요 이동 */}
      <nav aria-label="주요 화면" style={{ padding: '0 0 8px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        {navItems.map(item => (
          <button
            key={item.key}
            className="sn-row sn-nav"
            aria-current={item.active ? 'true' : undefined}
            onClick={item.onClick}
          >
            <span className="sn-icon" aria-hidden="true">{item.icon}</span>
            <span className="sn-row-text">{item.label}</span>
          </button>
        ))}
      </nav>

      {/* 노트 트리 */}
      <VoyageLog />

      {/* 설정 */}
      <div style={{ padding: '6px 0', borderTop: '1px solid var(--border)', flexShrink: 0 }}>
        <button
          className="sn-row sn-nav"
          aria-current={showSettings ? 'true' : undefined}
          onClick={() => setShowSettings(!showSettings)}
        >
          <span className="sn-icon" aria-hidden="true">⚙</span>
          <span className="sn-row-text">설정</span>
        </button>
      </div>
    </div>
  )
}
