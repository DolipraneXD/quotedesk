import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type {
  ApiKeysIn,
  Brand,
  Category,
  Dashboard,
  NoteRule,
  PriceRow,
  Product,
  ProductAlias,
  ProductInput,
  ProductList,
  ProductQuery,
  Settings,
} from './types'

export const keys = {
  products: ['products'] as const,
  product: (id: number) => ['products', id] as const,
  categories: ['categories'] as const,
  brands: ['brands'] as const,
  settings: ['settings'] as const,
  dashboard: ['dashboard'] as const,
}

export function useCategories() {
  return useQuery({
    queryKey: keys.categories,
    queryFn: () => api<Category[]>('GET', '/categories'),
    staleTime: 60_000,
  })
}

export function useBrands() {
  return useQuery({
    queryKey: keys.brands,
    queryFn: () => api<Brand[]>('GET', '/brands'),
    staleTime: 60_000,
  })
}

export function useProducts(query: ProductQuery) {
  return useQuery({
    queryKey: [...keys.products, 'list', query],
    queryFn: () => api<ProductList>('GET', '/products', { query: { ...query } }),
    placeholderData: (prev) => prev,
  })
}

export function useProduct(id: number) {
  return useQuery({
    queryKey: keys.product(id),
    queryFn: () => api<Product>('GET', `/products/${id}`),
    enabled: id > 0,
  })
}

export function usePriceHistory(id: number) {
  return useQuery({
    queryKey: [...keys.product(id), 'prices'],
    queryFn: () => api<PriceRow[]>('GET', `/products/${id}/prices`),
  })
}

export function useProductAliases(id: number) {
  return useQuery({
    queryKey: [...keys.product(id), 'aliases'],
    queryFn: () => api<ProductAlias[]>('GET', `/products/${id}/aliases`),
  })
}

export function useSettings() {
  return useQuery({ queryKey: keys.settings, queryFn: () => api<Settings>('GET', '/settings') })
}

export function useDashboard() {
  return useQuery({ queryKey: keys.dashboard, queryFn: () => api<Dashboard>('GET', '/dashboard') })
}

export function useNoteRules() {
  return useQuery({
    queryKey: ['note-rules'],
    queryFn: () => api<NoteRule[]>('GET', '/note-rules'),
  })
}

export type NoteRuleInput = Partial<Omit<NoteRule, 'id'>>

export function useNoteRuleMutations() {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ['note-rules'] })
  return {
    save: useMutation({
      mutationFn: ({ id, ...body }: NoteRuleInput & { id?: number }) =>
        id
          ? api<NoteRule>('PATCH', `/note-rules/${id}`, { body })
          : api<NoteRule>('POST', '/note-rules', { body }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<void>('DELETE', `/note-rules/${id}`),
      onSuccess: refresh,
    }),
  }
}

/** Any catalog write can change lists, counts and the dashboard: refresh them all. */
function useInvalidateCatalog() {
  const qc = useQueryClient()
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: keys.products }),
      qc.invalidateQueries({ queryKey: keys.categories }),
      qc.invalidateQueries({ queryKey: keys.brands }),
      qc.invalidateQueries({ queryKey: keys.dashboard }),
    ])
}

export function useSaveProduct() {
  const invalidate = useInvalidateCatalog()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: ProductInput }) =>
      id
        ? api<Product>('PATCH', `/products/${id}`, { body })
        : api<Product>('POST', '/products', { body }),
    onSuccess: invalidate,
  })
}

export function useDeleteProduct() {
  const invalidate = useInvalidateCatalog()
  return useMutation({
    mutationFn: (id: number) => api<void>('DELETE', `/products/${id}`),
    onSuccess: invalidate,
  })
}

export function useSetPrice() {
  const invalidate = useInvalidateCatalog()
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: number
      price_usd: string
      tier?: 'standard' | 'forecast'
      price_date?: string | null
      note?: string | null
    }) => api<Product>('POST', `/products/${id}/prices`, { body }),
    onSuccess: invalidate,
  })
}

export function useMergeProduct() {
  const invalidate = useInvalidateCatalog()
  return useMutation({
    mutationFn: ({ id, intoId }: { id: number; intoId: number }) =>
      api<Product>('POST', `/products/${id}/merge`, { body: { into_id: intoId } }),
    onSuccess: invalidate,
  })
}

export function useSaveCategory() {
  const invalidate = useInvalidateCatalog()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: Partial<Category> }) =>
      id
        ? api<Category>('PATCH', `/categories/${id}`, { body })
        : api<Category>('POST', '/categories', { body }),
    onSuccess: invalidate,
  })
}

export function useBrandMutations() {
  const invalidate = useInvalidateCatalog()
  const opts = { onSuccess: invalidate }
  return {
    create: useMutation({
      mutationFn: (body: { canonical: string; name_zh?: string; name_en?: string }) =>
        api<Brand>('POST', '/brands', { body }),
      ...opts,
    }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: number; body: Partial<Brand> }) =>
        api<Brand>('PATCH', `/brands/${id}`, { body }),
      ...opts,
    }),
    remove: useMutation({
      mutationFn: (id: number) => api<void>('DELETE', `/brands/${id}`),
      ...opts,
    }),
    addAlias: useMutation({
      mutationFn: ({ id, alias, lang }: { id: number; alias: string; lang: string }) =>
        api<Brand>('POST', `/brands/${id}/aliases`, { body: { alias, lang } }),
      ...opts,
    }),
    removeAlias: useMutation({
      mutationFn: ({ id, aliasId }: { id: number; aliasId: number }) =>
        api<Brand>('DELETE', `/brands/${id}/aliases/${aliasId}`),
      ...opts,
    }),
  }
}

export function useSaveSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<Settings> & ApiKeysIn) =>
      api<Settings>('PUT', '/settings', { body }),
    onSuccess: (data) => qc.setQueryData(keys.settings, data),
  })
}

export function useSaveLanguage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ui_language: 'en' | 'zh') =>
      api<Settings>('PUT', '/settings/language', { body: { ui_language } }),
    onSuccess: (data) => qc.setQueryData(keys.settings, data),
  })
}
