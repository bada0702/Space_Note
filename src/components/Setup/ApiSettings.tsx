import { useEffect, useState } from 'react'
import { GraphSettings } from './GraphSettings'
import { McpSettings } from './McpSettings'
import { useAIStore } from '../../store/aiStore'
import { useNotesStore } from '../../store/notesStore'
import { aiApi } from '../../api/aiApi'
import type { AISettings } from '../../types'
import { DEFAULT_MODEL, MODEL_OPTIONS } from '../../constants/models'

// 웹모드(브라우저)에는 Tauri 런타임 브리지가 없어 폴더 선택 대화상자를 띄울 수 없다.
// 이 체크 없이 열기를 시도하면 window.__TAURI_INTERNALS__가 없어 조용히 실패해
// 버튼이 아무 반응도 없는 것처럼 보인다.
function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
}

async function pickFolderViaTauri(): Promise<string | null> {
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const selected = await open({ directory: true, title: '노트 저장 폴더 선택' })
    return typeof selected === 'string' ? selected : null
  } catch {
    return null
  }
}

const MODEL_GROUPS = [...new Set(MODEL_OPTIONS.map(m => m.group))]

const TABS = [
  { key: 'general', label: '일반' },
  { key: 'ai', label: 'AI 모델' },
  { key: 'graph', label: '지식 그래프' },
  { key: 'mcp', label: 'MCP 서버' },
] as const
type SettingsTab = typeof TABS[number]['key']

export function ApiSettings({ onClose }: { onClose: () => void }) {
  const { loadSettings, saveSettings } = useAIStore()
  const [form, setForm] = useState<Partial<AISettings>>({})
  const [savedKeys, setSavedKeys] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [ollamaModels, setOllamaModels] = useState<{name: string}[] | null>(null)
  const [folderPickerHint, setFolderPickerHint] = useState(false)
  const [tab, setTab] = useState<SettingsTab>('general')

  const refreshSavedKeys = () => {
    const s = useAIStore.getState().settings
    if (!s) return
    setSavedKeys({
      anthropic_api_key: !!s.anthropic_api_key,
      openai_api_key: !!s.openai_api_key,
      google_api_key: !!s.google_api_key,
    })
  }

  useEffect(() => {
    loadSettings().then(() => {
      const s = useAIStore.getState().settings
      if (s) {
        // API 키는 빈칸으로 (저장된 값을 폼에 노출하지 않음)
        setForm({
          anthropic_api_key: '',
          openai_api_key: '',
          google_api_key: '',
          default_model: s.default_model,
          vault_dir: s.vault_dir ?? '',
        })
        refreshSavedKeys()
      }
    })
    aiApi.getOllamaModels()
      .then(setOllamaModels)
      .catch(e => { console.error('Failed to fetch Ollama models', e); setOllamaModels([]) })
  }, [])

  const setField = (k: keyof AISettings, v: string) =>
    setForm(f => ({ ...f, [k]: v }))

  const handleSave = async () => {
    setSaving(true)
    try {
      // 빈칸/마스킹된 키 필드는 전송하지 않음 — 저장된 키를 덮어쓰지 않게
      const patch: Partial<AISettings> = {}
      for (const [k, v] of Object.entries(form)) {
        if (v === undefined) continue
        const s = String(v)
        if (k.endsWith('_api_key') && (s === '' || s.startsWith('****'))) continue
        ;(patch as Record<string, string>)[k] = s
      }
      await saveSettings(patch)
      await loadSettings()

      if (patch.vault_dir) {
        const path = patch.vault_dir.trim()
        useNotesStore.getState().setVaultPath(path)
        localStorage.setItem('sn-vault-path', path)
        useNotesStore.setState({ activeNote: null })
        await useNotesStore.getState().fetchNotes()
      }

      refreshSavedKeys()
      setForm(f => ({
        ...f,
        anthropic_api_key: '',
        openai_api_key: '',
        google_api_key: '',
        vault_dir: form.vault_dir,
      }))
      setSaved(true)
      setTimeout(() => setSaved(false), 1500)
    } catch (e) {
      console.error('settings save failed:', e)
    } finally {
      setSaving(false)
    }
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '6px 10px', borderRadius: 5,
    background: 'var(--bg-input)', color: 'var(--text-primary)',
    border: '1px solid var(--border)', fontSize: 13, fontFamily: 'var(--font-mono)',
    outline: 'none', boxSizing: 'border-box',
  }
  const labelStyle: React.CSSProperties = {
    fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)',
    marginBottom: 6, display: 'block',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 헤더 */}
      <div className="sn-glass-bar" style={{ padding: '16px 24px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <span style={{ fontFamily: 'var(--font-title)', fontSize: 19, fontWeight: 700, color: 'var(--text-primary)' }}>
            시스템 설정
          </span>
          <button
            onClick={onClose}
            aria-label="설정 닫기"
            style={{ color: 'var(--text-secondary)', fontSize: 16, lineHeight: 1, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          >
            ✕
          </button>
        </div>
        <div className="sn-segment" role="group" aria-label="설정 항목">
          {TABS.map(t => (
            <button key={t.key} aria-pressed={tab === t.key} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
      <div style={{ maxWidth: 560 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {tab === 'general' && (
          <div>
            <label htmlFor="vault_dir" style={labelStyle}>노트 저장 경로 (Vault Dir)</label>
            <div style={{ display: 'flex', gap: 6 }}>
              <input
                id="vault_dir"
                type="text"
                placeholder="예: /path/to/notes"
                value={form.vault_dir ?? ''}
                onChange={e => setField('vault_dir', e.target.value)}
                style={inputStyle}
              />
              <button
                onClick={async () => {
                  if (!isTauri()) {
                    // 브라우저에는 절대경로를 주는 폴더 선택창이 없다 — 조용히 아무 반응 없는
                    // 대신, 입력창에 직접 타이핑하라는 걸 바로 알려주고 포커스를 옮겨준다.
                    setFolderPickerHint(true)
                    document.getElementById('vault_dir')?.focus()
                    return
                  }
                  const picked = await pickFolderViaTauri()
                  if (picked) {
                    setField('vault_dir', picked)
                    setFolderPickerHint(false)
                  }
                }}
                type="button"
                style={{
                  padding: '6px 12px',
                  background: 'var(--bg-input)',
                  color: 'var(--text-primary)',
                  border: '1px solid var(--border)',
                  borderRadius: 5,
                  fontSize: 12,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                찾아보기
              </button>
            </div>
            {folderPickerHint && (
              <p style={{ fontSize: 12, color: 'var(--text-secondary)', opacity: 0.7, marginTop: 4 }}>
                이 환경(웹 브라우저)에서는 폴더 선택 대화상자를 지원하지 않아요 — 위 입력창에 서버의 절대경로를 직접 입력하세요.
              </p>
            )}
          </div>
          )}

          {tab === 'ai' && (<>
          {[
            { key: 'anthropic_api_key' as const, label: 'Anthropic API Key (Claude)', placeholder: 'sk-ant-...' },
            { key: 'openai_api_key'    as const, label: 'OpenAI API Key (GPT)',       placeholder: 'sk-...' },
            { key: 'google_api_key'    as const, label: 'Google API Key (Gemini)',    placeholder: 'AIza...' },
          ].map(({ key, label, placeholder }) => (
            <div key={key}>
              <label htmlFor={key} style={labelStyle}>
                {label}
                {savedKeys[key] && (
                  <span style={{ color: '#2f9e44', marginLeft: 6, textTransform: 'none' }}>
                    ✓ 저장됨
                  </span>
                )}
              </label>
              <input
                id={key}
                type="password"
                placeholder={savedKeys[key] ? '저장된 키 유지 (변경할 때만 입력)' : placeholder}
                value={form[key] ?? ''}
                onChange={e => setField(key, e.target.value)}
                style={inputStyle}
              />
            </div>
          ))}

          <div>
            <label htmlFor="default_model" style={labelStyle}>채팅 모델</label>
            <select
              id="default_model"
              value={form.default_model ?? DEFAULT_MODEL}
              onChange={e => setField('default_model', e.target.value)}
              style={{ ...inputStyle, cursor: 'pointer' }}
            >
              {MODEL_GROUPS.map(g => (
                <optgroup key={g} label={g}>
                  {MODEL_OPTIONS.filter(m => m.group === g).map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </optgroup>
              ))}
              {ollamaModels && ollamaModels.length > 0 && (
                <optgroup label="Ollama (로컬)">
                  {ollamaModels.map(m => (
                    <option key={m.name} value={`ollama:${m.name}`}>{m.name}</option>
                  ))}
                </optgroup>
              )}
              {form.default_model && !MODEL_OPTIONS.find(m => m.value === form.default_model) && !ollamaModels?.find(m => `ollama:${m.name}` === form.default_model) && (
                <option value={form.default_model}>{form.default_model} (Unknown)</option>
              )}
            </select>
            {ollamaModels && (
              <p style={{ fontSize: 12, color: 'var(--text-secondary)', opacity: 0.7, marginTop: 4 }}>
                {ollamaModels.length > 0
                  ? `Ollama 로컬 모델 ${ollamaModels.length}개를 찾았습니다.`
                  : 'Ollama 서버에 연결되지 않았거나 설치된 모델이 없습니다 — Ollama를 실행하고 모델을 받은 뒤(ollama pull) 이 화면을 다시 여세요. 서버 주소는 백엔드 환경변수 OLLAMA_BASE_URL로 바꿀 수 있습니다.'}
              </p>
            )}
          </div>
          </>)}

          {tab === 'graph' && <GraphSettings />}
          {tab === 'mcp' && <McpSettings />}
        </div>

        {/* 지식 그래프·MCP 탭은 각자 동작 버튼을 가지므로 저장 버튼은 폼 탭에만 둔다 */}
        {(tab === 'general' || tab === 'ai') && (
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            marginTop: 20, width: '100%', padding: '9px',
            background: saved ? '#2f9e44' : 'var(--bg-input)',
            color: saved ? '#fff' : 'var(--text-secondary)', borderRadius: 6, fontSize: 13, fontWeight: 500,
            border: '1px solid var(--border)', cursor: saving ? 'wait' : 'pointer',
            transition: 'background 0.2s',
          }}
        >
          {saving ? '저장 중...' : saved ? '✓ 저장됨' : '저장'}
        </button>
        )}
      </div>
      </div>
    </div>
  )
}
