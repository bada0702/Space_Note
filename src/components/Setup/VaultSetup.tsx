import { useState, useEffect } from 'react'
import { useNotesStore } from '../../store/notesStore'

async function fetchDefaultVault(): Promise<string> {
  try {
    const res = await fetch('http://localhost:8001/health')
    const data = await res.json()
    return data.default_vault ?? ''
  } catch {
    return ''
  }
}

async function pickFolderViaTauri(): Promise<string | null> {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, title: '항해 기록 폴더 선택' })
    return typeof selected === 'string' ? selected : null
  } catch {
    return null
  }
}

export function VaultSetup({ onDone }: { onDone: () => void }) {
  const { setVaultPath } = useNotesStore()
  const [defaultVault, setDefaultVault] = useState('')
  const [manualPath, setManualPath] = useState('')
  const [showManual, setShowManual] = useState(false)

  useEffect(() => {
    fetchDefaultVault().then(p => {
      setDefaultVault(p)
      setManualPath(p)
    })
  }, [])

  const apply = (path: string) => {
    if (!path.trim()) return
    setVaultPath(path.trim())
    localStorage.setItem('sn-vault-path', path.trim())
    onDone()
  }

  const handlePickFolder = async () => {
    const picked = await pickFolderViaTauri()
    if (picked) {
      apply(picked)
    } else {
      // Tauri 없는 환경이면 수동 입력 모드로 전환
      setShowManual(true)
    }
  }

  return (
    <div className="flex flex-col items-center justify-center h-screen gap-4" style={{ background: 'var(--bg-app)' }}>
      <div className="flex items-center gap-3 mb-2">
        <svg width="36" height="36" viewBox="0 0 48 48" fill="none" style={{ color: 'var(--text-primary)' }}>
          <ellipse cx="24" cy="24" rx="22" ry="10" stroke="currentColor" strokeWidth="1.5" />
          <circle cx="24" cy="24" r="3" fill="currentColor" />
          <circle cx="6" cy="20" r="1" fill="currentColor" opacity="0.3" />
          <circle cx="42" cy="28" r="0.8" fill="currentColor" opacity="0.4" />
        </svg>
        <h1 style={{ fontSize: '24px', fontWeight: 600, color: 'var(--text-primary)' }}>SpaceNote</h1>
      </div>

      <p style={{ fontSize: '13px', color: 'var(--text-secondary)', textAlign: 'center', lineHeight: 1.6 }}>
        항해 기록을 저장할 폴더를 선택하세요
      </p>

      {/* 기본 경로 사용 */}
      {defaultVault && (
        <div style={{ textAlign: 'center' }}>
          <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '8px', opacity: 0.7 }}>
            기본 경로: <code style={{ background: 'var(--bg-input)', padding: '1px 6px', borderRadius: '3px' }}>{defaultVault}</code>
          </p>
          <button
            autoFocus
            onClick={() => apply(defaultVault)}
            style={{
              padding: '8px 24px',
              fontSize: '13px',
              fontWeight: 500,
              background: 'var(--text-primary)',
              color: 'var(--bg-app)',
              border: 'none',
              borderRadius: '3px',
              cursor: 'pointer',
              marginRight: '8px',
            }}
          >
            기본 경로 사용
          </button>
          <button
            onClick={handlePickFolder}
            style={{
              padding: '8px 16px',
              fontSize: '13px',
              color: 'var(--text-secondary)',
              background: 'transparent',
              border: '1px solid var(--border)',
              borderRadius: '3px',
              cursor: 'pointer',
            }}
          >
            다른 폴더 선택
          </button>
        </div>
      )}

      {/* Tauri 없음 + 기본 경로도 없는 경우 */}
      {!defaultVault && (
        <button
          autoFocus
          onClick={handlePickFolder}
          style={{
            marginTop: '8px',
            padding: '8px 24px',
            fontSize: '13px',
            fontWeight: 500,
            background: 'var(--text-primary)',
            color: 'var(--bg-app)',
            border: 'none',
            borderRadius: '3px',
            cursor: 'pointer',
          }}
        >
          폴더 선택
        </button>
      )}

      {/* 수동 경로 입력 */}
      {showManual && (
        <div style={{ display: 'flex', gap: '8px', marginTop: '4px', width: '380px' }}>
          <input
            autoFocus
            value={manualPath}
            onChange={e => setManualPath(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && apply(manualPath)}
            placeholder="예: C:\Users\이름\Documents\SpaceNote"
            style={{
              flex: 1,
              padding: '6px 10px',
              fontSize: '12px',
              background: 'var(--bg-input)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
              borderRadius: '3px',
              outline: 'none',
            }}
          />
          <button
            onClick={() => apply(manualPath)}
            style={{
              padding: '6px 14px',
              fontSize: '12px',
              background: 'var(--text-primary)',
              color: 'var(--bg-app)',
              border: 'none',
              borderRadius: '3px',
              cursor: 'pointer',
            }}
          >
            확인
          </button>
        </div>
      )}

      <p style={{ fontSize: '10px', color: 'var(--text-secondary)', opacity: 0.4, marginTop: '4px' }}>
        선택한 폴더에 .md 파일로 저장됩니다 — Obsidian 호환
      </p>
    </div>
  )
}
