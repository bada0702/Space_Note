import { useEffect, useState } from 'react'
import { aiApi } from '../../api/aiApi'
import { useAIStore } from '../../store/aiStore'
import { MODEL_OPTIONS } from '../../constants/models'
import type { GraphStatus } from '../../types'

const DEFAULT_GRAPH_MODEL = 'gemini-3.1-flash-lite'
const CLOUD_GROUPS = [...new Set(MODEL_OPTIONS.map(m => m.group))]

/** 설정 화면의 '지식 그래프' 항목 — 분석 진행 상황과 일괄 분석/재시도. */
export function GraphSettings() {
  const [status, setStatus] = useState<GraphStatus | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const { settings, loadSettings } = useAIStore()
  const [ollamaNames, setOllamaNames] = useState<string[]>([])
  const graphModel = settings?.graph_model || DEFAULT_GRAPH_MODEL
  const modelLabel = graphModel.startsWith('ollama:')
    ? `Ollama ${graphModel.slice('ollama:'.length)}`
    : MODEL_OPTIONS.find(m => m.value === graphModel)?.label ?? graphModel

  const refresh = () =>
    aiApi.getGraphStatus()
      .then(s => { setStatus(s); setError('') })
      .catch(() => setError('지식 그래프 상태를 불러오지 못했습니다. 백엔드가 실행 중인지 확인하세요.'))

  useEffect(() => {
    loadSettings()
    aiApi.getOllamaModels().then(list => setOllamaNames(list.map(m => m.name))).catch(() => setOllamaNames([]))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 추출 모델은 고르는 즉시 저장 — 다음 분석부터 적용된다
  const changeModel = async (value: string) => {
    await aiApi.patchSettings({ graph_model: value })
    await loadSettings()
  }
  const ollamaOptions = [...new Set([...ollamaNames, ...(settings?.ollama_custom_models ?? [])])]

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 5000) // 설정 창이 열려 있는 동안 5초마다 갱신
    return () => clearInterval(timer)
  }, [])

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true)
    try { await action(); await refresh() } catch { setError('요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요.') }
    finally { setBusy(false) }
  }

  const handleRebuild = () => {
    if (!status) return
    const minutes = Math.ceil(status.total / status.rate_per_minute)
    const ok = confirm(
      `노트 ${status.total}개를 다시 분석합니다.\n` +
      `약 ${minutes}분 걸리고 ${modelLabel} 모델을 사용합니다. 분석은 백그라운드에서 진행되며, 그동안 앱을 계속 쓸 수 있습니다.`
    )
    if (ok) run(aiApi.rebuildGraph)
  }

  return (
    <div className="sn-graph-settings">
      <div className="sn-graph-head">
        <span>지식 그래프</span>
        {status && <span className="sn-graph-meta">개념 {status.concepts}개, 관계 {status.relations}개</span>}
      </div>
      <p className="sn-graph-desc">
        노트에서 개념과 관계를 뽑아 AI 채팅이 관련 노트를 더 정확히 찾게 합니다. 고친 노트는 편집을 멈추고 1분 뒤 자동으로 다시 분석됩니다.
      </p>

      {status && (
        <dl className="sn-graph-counts">
          <div><dt>완료</dt><dd>{status.done}</dd></div>
          <div><dt>대기</dt><dd>{status.pending}</dd></div>
          <div><dt>실패</dt><dd className={status.failed ? 'is-failed' : undefined}>{status.failed}</dd></div>
          <div><dt>미분석</dt><dd>{status.idle}</dd></div>
        </dl>
      )}
      {status && status.pending > 0 && (
        <p className="sn-graph-desc">분석 중 — 남은 시간 약 {status.eta_minutes}분</p>
      )}
      {error && <p role="alert" className="sn-graph-error">{error}</p>}

      <label htmlFor="graph_model" className="sn-graph-head" style={{ marginTop: 12, display: 'block' }}>
        추출 모델
      </label>
      <select
        id="graph_model"
        value={graphModel}
        onChange={e => changeModel(e.target.value)}
        style={{
          marginTop: 6, width: '100%', padding: '6px 10px', borderRadius: 5, boxSizing: 'border-box',
          background: 'var(--bg-input)', color: 'var(--text-primary)', border: '1px solid var(--border)', fontSize: 13,
        }}
      >
        {CLOUD_GROUPS.map(group => (
          <optgroup key={group} label={group}>
            {MODEL_OPTIONS.filter(m => m.group === group).map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
          </optgroup>
        ))}
        {ollamaOptions.length > 0 && (
          <optgroup label="Ollama (로컬)">
            {ollamaOptions.map(name => <option key={name} value={`ollama:${name}`}>{name}</option>)}
          </optgroup>
        )}
      </select>
      <p className="sn-graph-desc">
        노트를 Class·Instance·Literal 온톨로지로 뽑는 모델입니다. Ollama를 고르면 노트가 외부로 나가지 않습니다.
      </p>

      <div className="sn-graph-actions">
        <button type="button" className="sn-btn" onClick={handleRebuild} disabled={busy || !status}>
          전체 다시 분석
        </button>
        {status && status.pending > 0 && (
          <button type="button" className="sn-btn" onClick={() => run(aiApi.cancelGraph)} disabled={busy}>
            분석 취소
          </button>
        )}
        {status && status.failed > 0 && (
          <button type="button" className="sn-btn" onClick={() => run(aiApi.retryFailedGraph)} disabled={busy}>
            실패한 노트만 다시 시도
          </button>
        )}
      </div>
    </div>
  )
}
