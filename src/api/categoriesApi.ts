import { apiFetch } from './client'
import type { Category } from '../types'

export const categoriesApi = {
  list: () => apiFetch<Category[]>('/categories'),
  create: (name: string, color?: string) =>
    apiFetch<Category>('/categories', { method: 'POST', body: JSON.stringify({ name, color }) }),
  update: (id: string, patch: Partial<Pick<Category, 'name' | 'color' | 'sort_order'>>) =>
    apiFetch<Category>(`/categories/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  delete: (id: string) =>
    apiFetch<void>(`/categories/${id}`, { method: 'DELETE' }),
}
