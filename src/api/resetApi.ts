import { apiFetch } from './client'

export interface ResetPreview {
  notes: number
  categories: number
  conversations: number
  files: number
  vault_dir: string
}

export const RESET_CONFIRM_TEXT = '초기화'

export const resetApi = {
  preview: (): Promise<ResetPreview> => apiFetch('/reset/preview'),
  reset: (): Promise<{ ok: boolean }> =>
    apiFetch('/reset', { method: 'POST', body: JSON.stringify({ confirm: RESET_CONFIRM_TEXT }) }),
}
