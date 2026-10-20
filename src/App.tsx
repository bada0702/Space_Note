import { useEffect, useState } from 'react'
import { ThemeProvider } from './components/Layout/ThemeProvider'
import { AppLayout } from './components/Layout/AppLayout'
import { Sidebar } from './components/Sidebar/Sidebar'
import { EditorTabs } from './components/Editor/EditorTabs'
import { NoteEditor } from './components/Editor/NoteEditor'
import { NotePreview } from './components/Editor/NotePreview'
import { VaultSetup } from './components/Setup/VaultSetup'
import { StarMapCanvas } from './components/StarMap/StarMapCanvas'
import { ChatPanel } from './components/AI/ChatPanel'
import { SearchPanel } from './components/Navigation/SearchPanel'
import { DiscoveriesPanel } from './components/Navigation/DiscoveriesPanel'
import { ConstellationsPanel } from './components/Navigation/ConstellationsPanel'
import { ApiSettings } from './components/Setup/ApiSettings'
import { useNotesStore } from './store/notesStore'
import { useAIStore } from './store/aiStore'
import { useSearchStore } from './store/searchStore'
import { aiApi } from './api/aiApi'

/** 메인 영역에 성도가 보이는 상태인지 — 레이아웃(유리 카드 여부)과 MainPanel이 함께 쓴다 */
function useIsMapView() {
  const { activeTab } = useNotesStore()
  const { panelOpen, showSettings } = useAIStore()
  const { activePanel } = useSearchStore()
  return !showSettings && !panelOpen && !activePanel && activeTab === 'starmap'
}

function MainPanel() {
  const { activeTab } = useNotesStore()
  const { panelOpen, showSettings, setShowSettings } = useAIStore()
  const { activePanel } = useSearchStore()

  // 패널은 하나만 표시 — 명시적 단일 렌더링으로 겹침 방지
  if (showSettings) return <ApiSettings onClose={() => setShowSettings(false)} />
  if (panelOpen) return <ChatPanel />
  if (activePanel === 'search') return <SearchPanel />
  if (activePanel === 'discoveries') return <DiscoveriesPanel />
  if (activePanel === 'constellations') return <ConstellationsPanel />

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <EditorTabs />
      <div className="flex-1 overflow-hidden">
        {activeTab === 'edit' && <NoteEditor />}
        {activeTab === 'preview' && <NotePreview />}
        {activeTab === 'starmap' && <StarMapCanvas />}
      </div>
    </div>
  )
}

function SettingsAwareLayout() {
  const isMap = useIsMapView()
  return <AppLayout sidebar={<Sidebar />} main={<MainPanel />} isMap={isMap} />
}

function AppContent() {
  const { setVaultPath } = useNotesStore()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const saved = localStorage.getItem('sn-vault-path')
    if (saved) {
      setVaultPath(saved)
      aiApi.patchSettings({ vault_dir: saved }).catch(e => console.error('Failed to sync vault path on load:', e))
      setReady(true)
    }
  }, [])

  if (!ready) return <VaultSetup onDone={() => setReady(true)} />

  return <SettingsAwareLayout />
}

function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  )
}

export default App
