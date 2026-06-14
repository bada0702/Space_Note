import { useEffect, useState } from 'react'
import { useAIStore } from '../../store/aiStore'
import type { AISettings } from '../../types'

const MODEL_OPTIONS = [
  { value: 'claude-sonnet-4-6',   label: 'Claude Sonnet 4.6' },
  { value: 'claude-haiku-4-5',    label: 'Claude Haiku 4.5' },
  { value: 'gemini-2.0-flash',    label: 'Gemini 2.0 Flash' },
  { value: 'gpt-4o-mini',         label: 'GPT-4o mini' },
  { value: 'gpt-4o',              label: 'GPT-4o' },
]

export function ApiSettings({ onClose }: { onClose: () => void }) {
  const { loadSettings, saveSettings } = useAIStore()
  const [form, setForm] = useState<Partial<AISettings>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    loadSettings().then(() => {
      const s = useAIStore.getState().settings
      if (s) {
        // API 키는 빈칸으로 (마스킹된 값을 폼에 넣지 않음)
        setForm({
          anthropic_api_key: '',
          openai_api_key: '',
          google_api_key: '',
          default_model: s.default_model,
        })
      }
    })
  }, [])

  const setField = (k: keyof AISettings, v: string) =>
    setForm(f => ({ ...f, [k]: v }))

  const handleSave = async () => {
    setSaving(true)
    try {
      // "****"로 시작하는 마스킹된 값은 전송하지 않음
      const patch: Partial<AISettings> = {}
      for (const [k, v] of Object.entries(form)) {
        if (v !== undefined && !String(v).startsWith('****')) {
          (patch as Record<string, string>)[k] = v
        }
      }
      await saveSettings(patch)
      setSaved(true)
      setTimeout(() => setSaved(false), 1500)
    } catch {
      // 저장 실패 시 무시
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
              <label htmlFor={key} style={labelStyle}>{label}</label>
              <input
                id={key}
                type="password"
                placeholder={placeholder}
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
