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
import { TagsPanel } from './components/Navigation/TagsPanel'
import { ApiSettings } from './components/Setup/ApiSettings'
import { useNotesStore } from './store/notesStore'
import { useAIStore } from './store/aiStore'
import { useSearchStore } from './store/searchStore'

function MainPanel() {
  const { activeTab } = useNotesStore()
  const { panelOpen } = useAIStore()
  const { activePanel } = useSearchStore()

  // 패널은 하나만 표시 — 명시적 단일 렌더링으로 겹침 방지
  if (panelOpen) return <ChatPanel />
  if (activePanel === 'search') return <SearchPanel />
  if (activePanel === 'discoveries') return <DiscoveriesPanel />
  if (activePanel === 'tags') return <TagsPanel />

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <EditorTabs />
      <div
        className="flex-1 overflow-hidden"
        style={{ background: activeTab === 'starmap' ? '#020408' : 'var(--bg-app)' }}
      >
        {activeTab === 'edit' && <NoteEditor />}
        {activeTab === 'preview' && <NotePreview />}
        {activeTab === 'starmap' && <StarMapCanvas />}
      </div>
    </div>
  )
}

function SettingsAwareLayout() {
  const { showSettings, setShowSettings } = useAIStore()
  return (
    <>
      <AppLayout sidebar={<Sidebar />} main={<MainPanel />} />
      {showSettings && <ApiSettings onClose={() => setShowSettings(false)} />}
    </>
  )
}

function AppContent() {
  const { setVaultPath } = useNotesStore()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const saved = localStorage.getItem('sn-vault-path')
    if (saved) {
      setVaultPath(saved)
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
