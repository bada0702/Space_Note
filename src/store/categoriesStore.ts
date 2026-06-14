import { create } from 'zustand'
import type { Category } from '../types'
import { categoriesApi } from '../api/categoriesApi'

interface CategoriesState {
  categories: Category[]
  loading: boolean
  fetchCategories: () => Promise<void>
  addCategory: (name: string, color?: string) => Promise<Category>
  updateCategory: (id: string, patch: Partial<Pick<Category, 'name' | 'color'>>) => Promise<void>
  deleteCategory: (id: string) => Promise<void>
}

export const useCategoriesStore = create<CategoriesState>((set, get) => ({
  categories: [],
  loading: false,

  fetchCategories: async () => {
    set({ loading: true })
    const categories = await categoriesApi.list()
    set({ categories, loading: false })
  },

  addCategory: async (name, color) => {
    const cat = await categoriesApi.create(name, color)
    set(s => ({ categories: [...s.categories, cat] }))
    return cat
  },

  updateCategory: async (id, patch) => {
    const updated = await categoriesApi.update(id, patch)
    set(s => ({ categories: s.categories.map(c => c.id === id ? updated : c) }))
  },

  deleteCategory: async (id) => {
    await categoriesApi.delete(id)
    set(s => ({ categories: s.categories.filter(c => c.id !== id) }))
  },
}))
