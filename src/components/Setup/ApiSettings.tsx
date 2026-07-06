import { useEffect, useState } from 'react'
import { useAIStore } from '../../store/aiStore'
import type { AISettings } from '../../types'

const MODEL_OPTIONS = [
  { value: 'claude-sonnet-4-6',   label: 'Claude Sonnet 4.6' },
  { value: 'claude-haiku-4-5',    label: 'Claude Haiku 4.5' },
  { value: 'gemini-2.5-flash',    label: 'Gemini 2.5 Flash' },
]

export function ApiSettings({ onClose }: { onClose: () => void }) {
  const { loadSettings, saveSettings } = useAIStore()
  const [form, setForm] = useState<Partial<AISettings>>({})
  const [savedKeys, setSavedKeys] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

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
        })
        refreshSavedKeys()
      }
    })
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
      refreshSavedKeys()
      setForm(f => ({
        ...f,
        anthropic_api_key: '',
        openai_api_key: '',
        google_api_key: '',
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
    border: '1px solid var(--border)', fontSize: 12, fontFamily: 'monospace',
    outline: 'none', boxSizing: 'border-box',
  }
  const labelStyle: React.CSSProperties = {
    fontSize: 11, color: 'var(--text-secondary)', letterSpacing: '0.06em',
    textTransform: 'uppercase', marginBottom: 4, display: 'block',
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'rgba(0,0,0,0.65)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--bg-panel)', border: '1px solid var(--border)',
          borderRadius: 12, padding: '24px 28px', width: 420, maxWidth: '90vw',
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
          <span style={{ fontWeight: 600, fontSize: 15, color: 'var(--text-primary)' }}>
            AI 설정
          </span>
          <button
            onClick={onClose}
            style={{ color: 'var(--text-secondary)', fontSize: 16, lineHeight: 1, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          >
            ✕
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
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
            <label htmlFor="default_model" style={labelStyle}>기본 모델</label>
            <select
              id="default_model"
              value={form.default_model ?? 'claude-sonnet-4-6'}
              onChange={e => setField('default_model', e.target.value)}
              style={{ ...inputStyle, cursor: 'pointer' }}
            >
              {MODEL_OPTIONS.map(m => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>
        </div>

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
      </div>
    </div>
  )
}
