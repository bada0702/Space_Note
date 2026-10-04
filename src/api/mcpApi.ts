import { apiFetch } from './client'
import type { McpConfig } from '../types'

export const mcpApi = {
  getConfig: () => apiFetch<McpConfig>('/mcp/config'),
  patchConfig: (patch: Partial<Pick<McpConfig, 'enabled' | 'allow_write' | 'aibot_config'>>) =>
    apiFetch<McpConfig>('/mcp/config', { method: 'PATCH', body: JSON.stringify(patch) }),
  rotateToken: () => apiFetch<McpConfig>('/mcp/token/rotate', { method: 'POST' }),
  registerAibot: () => apiFetch<McpConfig>('/mcp/register-aibot', { method: 'POST' }),
}
