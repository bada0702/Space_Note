import { VoyageLog } from './VoyageLog'
import { useNotesStore } from '../../store/notesStore'
import { useAIStore } from '../../store/aiStore'
import { useSearchStore } from '../../store/searchStore'

export function Sidebar() {
  const { setTab, setStarMapFilter, activeTab, starMapFilter } = useNotesStore()
  const { panelOpen, setPanelOpen, setShowSettings } = useAIStore()
  const { activePanel, setPanel } = useSearchStore()

  // 각 버튼 클릭 시 나머지 패널을 모두 닫고 해당 항목만 활성화
  const closeAll = () => {
    setPanelOpen(false)
    setPanel(null)
  }

  const handleStarMap = () => {
    closeAll()
    setStarMapFilter(null)
    setTab('starmap')
  }

  const handleNavPanel = (id: 'discoveries' | 'search' | 'tags') => {
    const isAlreadyOpen = activePanel === id && !panelOpen
    closeAll()
    if (!isAlreadyOpen) setPanel(id)
  }

  const handleAIChat = () => {
    const isAlreadyOpen = panelOpen
    closeAll()
    if (!isAlreadyOpen) setPanelOpen(true)
  }

  // 활성 상태: 다른 패널이 열려 있으면 해당 항목은 비활성
  const isStarMapActive = activeTab === 'starmap' && starMapFilter === null && !panelOpen && !activePanel

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      <VoyageLog />

      {/* 하단 메뉴 */}
      <div className="py-2 space-y-0.5" style={{ borderTop: '1px solid var(--glass-border)' }}>
        <button
          className="w-full text-left px-4 py-1.5"
          onClick={handleStarMap}
          style={{
            fontSize: '13px',
            color: isStarMapActive ? 'var(--text-primary)' : 'var(--text-secondary)',
            borderLeft: isStarMapActive ? '2px solid var(--accent-line)' : '2px solid transparent',
            paddingLeft: isStarMapActive ? '14px' : '16px',
            transition: 'all 0.15s',
          }}
        >
          ✦ 성도
        </button>
        {[
          { id: 'discoveries' as const, icon: '⟡', label: '미개척 항로' },
          { id: 'search' as const,      icon: '⊕', label: '항법' },
          { id: 'tags' as const,        icon: '#', label: '태그' },
        ].map(item => (
          <button
            key={item.id}
            className="w-full text-left px-4 py-1.5"
            onClick={() => handleNavPanel(item.id)}
            style={{
              fontSize: '13px',
              color: activePanel === item.id && !panelOpen ? 'var(--text-primary)' : 'var(--text-secondary)',
              borderLeft: activePanel === item.id && !panelOpen ? '2px solid var(--accent-line)' : '2px solid transparent',
              paddingLeft: activePanel === item.id && !panelOpen ? '14px' : '16px',
              transition: 'all 0.15s',
            }}
          >
            <span style={{ fontSize: item.id === 'search' ? '3px' : '11px' }}>{item.icon}</span> {item.label}
          </button>
        ))}
        <button
          className="w-full text-left px-4 py-1.5"
          onClick={handleAIChat}
          style={{
            fontSize: '13px',
            color: panelOpen ? 'var(--text-primary)' : 'var(--text-secondary)',
            borderLeft: panelOpen ? '2px solid var(--accent-line)' : '2px solid transparent',
            paddingLeft: panelOpen ? '14px' : '16px',
            transition: 'all 0.15s',
          }}
        >
          ◈ AI 채팅
        </button>
        <button
          className="w-full text-left px-4 py-1.5"
          onClick={() => setShowSettings(true)}
          style={{ fontSize: '13px', color: 'var(--text-secondary)' }}
        >
          ⚙ 설정
        </button>
      </div>
    </div>
  )
}
