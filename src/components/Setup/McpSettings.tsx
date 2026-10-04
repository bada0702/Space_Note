import { useEffect, useState } from 'react'
import { mcpApi } from '../../api/mcpApi'
import type { McpConfig } from '../../types'

// http(비 localhost) 접속에서는 navigator.clipboard가 없어 execCommand로 대체한다.
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    ta.remove()
    return ok
  }
}

/** 설정 화면의 'MCP 서버' 항목 — aibot 등 외부 에이전트가 노트를 검색·조회하도록 연결. */
export function McpSettings() {
  const [cfg, setCfg] = useState<McpConfig | null>(null)
  const [aibotPath, setAibotPath] = useState('')
  const [showToken, setShowToken] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const apply = (c: McpConfig) => { setCfg(c); setAibotPath(c.aibot_config); setError('') }

  useEffect(() => {
    mcpApi.getConfig().then(apply)
      .catch(() => setError('MCP 설정을 불러오지 못했습니다. 백엔드가 실행 중인지 확인하세요.'))
  }, [])

  const run = async (action: () => Promise<McpConfig>, done?: string) => {
    setBusy(true)
    setNotice('')
    try {
      apply(await action())
      if (done) setNotice(done)
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^API \d+: /, '') : '요청을 처리하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  const copy = async (text: string, what: string) =>
    setNotice((await copyText(text)) ? `${what} 복사됨` : '복사하지 못했습니다 — 직접 선택해 복사하세요')

  const handleRotate = () => {
    const ok = confirm('토큰을 새로 만들면 기존 토큰으로 연결한 에이전트는 끊깁니다. 계속할까요?')
    if (ok) run(mcpApi.rotateToken, '새 토큰 발급됨 — aibot에 다시 등록하세요')
  }

  const handleRegister = async () => {
    if (aibotPath !== cfg?.aibot_config) await mcpApi.patchConfig({ aibot_config: aibotPath })
    run(mcpApi.registerAibot, 'aibot에 등록됨 — aibot을 재시작하면 도구가 적용됩니다')
  }

  const snippet = cfg?.client_config ? JSON.stringify(cfg.client_config, null, 2) : ''

  return (
    <div className="sn-graph-settings">
      <div className="sn-graph-head">
        <span>MCP 서버 (에이전트 연동)</span>
        {cfg?.enabled && <span className="sn-graph-meta">도구 {cfg.tools.length}개</span>}
      </div>
      <p className="sn-graph-desc">
        aibot 같은 AI 에이전트가 MCP로 노트를 검색하고 읽을 수 있게 합니다.
      </p>

      {cfg && (
        <>
          <label className="sn-mcp-toggle">
            <input type="checkbox" checked={cfg.enabled} disabled={busy}
              onChange={e => run(() => mcpApi.patchConfig({ enabled: e.target.checked }))} />
            MCP 서버 사용
          </label>
          <label className="sn-mcp-toggle">
            <input type="checkbox" checked={cfg.allow_write} disabled={busy || !cfg.enabled}
              onChange={e => run(() => mcpApi.patchConfig({ allow_write: e.target.checked }))} />
            에이전트의 노트 작성 허용 (create_note)
          </label>

          {cfg.enabled && cfg.token && (
            <>
              <div className="sn-mcp-field">
                <span>엔드포인트</span>
                <div className="sn-mcp-row">
                  <input readOnly value={cfg.url} onFocus={e => e.target.select()} />
                  <button type="button" className="sn-btn" onClick={() => copy(cfg.url, 'URL')}>복사</button>
                </div>
              </div>

              <div className="sn-mcp-field">
                <span>토큰 (Authorization: Bearer)</span>
                <div className="sn-mcp-row">
                  <input readOnly type={showToken ? 'text' : 'password'} value={cfg.token}
                    onFocus={e => e.target.select()} />
                  <button type="button" className="sn-btn" onClick={() => setShowToken(v => !v)}>
                    {showToken ? '숨기기' : '보기'}
                  </button>
                  <button type="button" className="sn-btn" onClick={() => copy(cfg.token, '토큰')}>복사</button>
                </div>
              </div>

              <div className="sn-mcp-field">
                <span>클라이언트 설정 (mcp_servers.json / Claude Desktop 형식)</span>
                <pre className="sn-mcp-snippet">{showToken ? snippet : snippet.replace(cfg.token, '••••••••')}</pre>
              </div>

              <div className="sn-mcp-field">
                <span>
                  aibot 설정 파일
                  {cfg.aibot_registered && <span className="sn-mcp-ok"> ✓ 등록됨</span>}
                </span>
                <div className="sn-mcp-row">
                  <input value={aibotPath} onChange={e => setAibotPath(e.target.value)}
                    placeholder="/root/aibot/data/mcp_servers.json" />
                  <button type="button" className="sn-btn is-primary" onClick={handleRegister}
                    disabled={busy || !aibotPath.trim()}>
                    aibot에 등록
                  </button>
                </div>
              </div>

              <div className="sn-graph-actions">
                <button type="button" className="sn-btn" onClick={() => copy(snippet, '설정 JSON')}>설정 JSON 복사</button>
                <button type="button" className="sn-btn is-danger" onClick={handleRotate} disabled={busy}>토큰 재발급</button>
              </div>
            </>
          )}
        </>
      )}
      {notice && <p className="sn-graph-desc">{notice}</p>}
      {error && <p role="alert" className="sn-graph-error">{error}</p>}
    </div>
  )
}
