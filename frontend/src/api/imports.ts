import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api } from './client'
import { keys } from './hooks'
import type { Money, ProductStatus } from './types'

export type ImportStatus =
  'uploaded' | 'extracting' | 'review' | 'committed' | 'reverted' | 'failed' | 'cancelled'

export type RowStatus = 'new' | 'updated' | 'unchanged' | 'possible_match' | 'problem'
export type RowDecision = 'create' | 'update' | 'skip'

export type SourceKind = 'sheet' | 'image' | 'pdf_page'

/** A sheet of a workbook, a screenshot, or a PDF page: one selectable source. */
export interface SheetSummary {
  name: string
  kind: SourceKind
  file?: string
  width?: number
  height?: number
  page?: number
  scanned?: boolean
  hidden: boolean
  rows: number
  columns: number
  looks_like_price_table: boolean
  preselected: boolean
  header_row: number | null
  currency: string | null
  fx_rate: string | null
  preview: string[][]
}

/** Fields a column can be mapped to, besides the name columns and category attributes. */
export const MAPPED_FIELDS = [
  'price',
  'erp_code',
  'mpn',
  'brand',
  'name_en',
  'stock_qty',
  'demand_qty',
  'stock_after_qty',
  'notes_raw',
  'platform',
] as const
export type MappedField = (typeof MAPPED_FIELDS)[number]

/** Importing a sheet without the AI: which column holds what. */
export interface ColumnMapping {
  sheet: string
  header_row: number
  category_code: string
  name_columns: string[]
  fields: Partial<Record<MappedField, string>>
  attributes: Record<string, string>
  currency: 'USD' | 'CNY'
  fx_rate?: string | null
}

export interface SheetColumn {
  letter: string
  header: string
  samples: string[]
}

export function useSheetColumns(importId: number, sheet: string, headerRow: number | null) {
  return useQuery({
    queryKey: ['imports', importId, 'columns', sheet, headerRow],
    queryFn: () =>
      api<SheetColumn[]>('GET', `/imports/${importId}/columns`, {
        query: { sheet, header_row: headerRow ?? 1 },
      }),
    enabled: Boolean(headerRow),
    staleTime: Infinity,
  })
}

export interface ImportProgress {
  total_chunks?: number
  done_chunks?: number
  failed_chunks?: number
  sheets?: Record<string, { total: number; done: number }>
  errors?: { sheet: string; rows: string; message: string }[]
}

export interface ImportStats {
  new?: number
  updated?: number
  unchanged?: number
  possible_match?: number
  problem?: number
  total?: number
  to_apply?: number
  committed?: { new: number; updated: number; unchanged: number; skipped: number }
  /** configurations created or refreshed from complete units (整机 BOMs) */
  configurations?: { id: number; created: boolean }[]
}

export interface ImportRecord {
  id: number
  filename: string
  file_type: string
  status: ImportStatus
  sheets: SheetSummary[]
  sheets_selected: string[]
  hints: Record<string, string>
  progress: ImportProgress
  stats: ImportStats
  llm_model: string | null
  llm_tokens_in: number
  llm_tokens_out: number
  error: string | null
  created_at: string
  started_at: string | null
  committed_at: string | null
}

export interface StagedPrice {
  tier: 'standard' | 'forecast'
  price_usd: Money
  amount_original: Money | null
  currency_original: string | null
  fx_rate: Money | null
  price_date: string | null
  source_ref: string
}

export interface Staged {
  category_id?: number
  category_code?: string
  name_zh?: string
  name_en?: string | null
  brand_id?: number | null
  brand_name?: string | null
  brand_new?: boolean
  attributes?: Record<string, string | number | boolean>
  erp_code?: string | null
  erp_code_alt?: string[]
  mpn?: string | null
  fields?: { status: ProductStatus } & Record<string, unknown>
  prices?: StagedPrice[]
  no_price_reason?: string | null
  diff?: {
    prices: Record<string, { old: Money | null; new: Money; pct: string | null }>
    fields: string[]
  }
}

export interface ExtractedRow {
  category_code: string
  name_zh: string
  name_en: string | null
  brand: string | null
  erp_codes: string[]
  mpn: string | null
  attributes: { key: string; value: string }[]
  notes_raw: string | null
  no_price_reason: string | null
}

export interface Issue {
  code: string
  [param: string]: string
}

export interface ImportRow {
  id: number
  sheet: string | null
  row_index: number
  source_ref: string | null
  raw: Record<string, string>
  parsed: { source: ExtractedRow; staged?: Staged }
  user_edits: Record<string, unknown>
  status: RowStatus
  decision: RowDecision | null
  match_type: string | null
  matched_product_id: number | null
  candidates: { product_id: number; name_zh: string; score: number }[]
  issues: Issue[]
  confidence: number | null
}

export interface RowList {
  items: ImportRow[]
  total: number
  counts: Partial<Record<RowStatus, number>>
}

export interface RowQuery {
  status?: RowStatus
  sheet?: string
  category?: string
  q?: string
  page?: number
  page_size?: number
}

const importKey = (id: number) => ['imports', id] as const

export function useImports() {
  return useQuery({
    queryKey: ['imports'],
    queryFn: () => api<ImportRecord[]>('GET', '/imports'),
  })
}

/** Polls every second while extraction runs. */
export function useImport(id: number) {
  return useQuery({
    queryKey: importKey(id),
    queryFn: () => api<ImportRecord>('GET', `/imports/${id}`),
    refetchInterval: (query) => (query.state.data?.status === 'extracting' ? 1000 : false),
  })
}

export function useImportRows(id: number, query: RowQuery, enabled: boolean) {
  return useQuery({
    queryKey: [...importKey(id), 'rows', query],
    queryFn: () => api<RowList>('GET', `/imports/${id}/rows`, { query: { ...query } }),
    enabled,
    placeholderData: (prev) => prev,
  })
}

export const SPREADSHEET_TYPES = ['xlsx', 'csv']

export function isSpreadsheet(record: ImportRecord): boolean {
  return SPREADSHEET_TYPES.includes(record.file_type)
}

export function sourceImageUrl(importId: number, index: number): string {
  return `/api/v1/imports/${importId}/sources/${index}/image`
}

/** One spreadsheet, or several screenshots / PDFs that become one import. */
export async function uploadImport(files: File[]): Promise<ImportRecord> {
  const body = new FormData()
  for (const file of files) body.append('files', file)
  const res = await fetch('/api/v1/imports', { method: 'POST', body })
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    throw new ApiError(
      res.status,
      data?.key ?? 'error.unknown',
      data?.detail ?? res.statusText,
      data?.params ?? {},
    )
  }
  return data as ImportRecord
}

function useInvalidateImport(id: number) {
  const qc = useQueryClient()
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: importKey(id) }),
      qc.invalidateQueries({ queryKey: ['imports'] }),
    ])
}

export function useImportActions(id: number) {
  const qc = useQueryClient()
  const invalidate = useInvalidateImport(id)
  const invalidateCatalog = () =>
    Promise.all([
      invalidate(),
      qc.invalidateQueries({ queryKey: keys.products }),
      qc.invalidateQueries({ queryKey: keys.brands }),
      qc.invalidateQueries({ queryKey: keys.categories }),
      qc.invalidateQueries({ queryKey: keys.dashboard }),
    ])
  return {
    extract: useMutation({
      mutationFn: (body: { sheets: string[]; hints: Record<string, string> }) =>
        api<ImportRecord>('POST', `/imports/${id}/extract`, { body }),
      onSuccess: invalidate,
    }),
    map: useMutation({
      mutationFn: (body: ColumnMapping) =>
        api<ImportRecord>('POST', `/imports/${id}/map`, { body }),
      onSuccess: invalidate,
    }),
    cancel: useMutation({
      mutationFn: () => api<ImportRecord>('POST', `/imports/${id}/cancel`),
      onSuccess: invalidate,
    }),
    patchRow: useMutation({
      mutationFn: ({
        rowId,
        ...body
      }: {
        rowId: number
        decision?: RowDecision
        edits?: Record<string, unknown>
      }) => api<ImportRow>('PATCH', `/imports/${id}/rows/${rowId}`, { body }),
      onSuccess: invalidate,
    }),
    bulk: useMutation({
      mutationFn: (body: {
        action: 'skip' | 'accept' | 'skip_unchanged' | 'accept_updates' | 'set_category'
        row_ids?: number[]
        category_code?: string
      }) => api<Record<string, number>>('POST', `/imports/${id}/bulk`, { body }),
      onSuccess: invalidate,
    }),
    commit: useMutation({
      mutationFn: () => api<ImportRecord>('POST', `/imports/${id}/commit`),
      onSuccess: invalidateCatalog,
      onError: invalidate, // per-row commit errors are stored on the rows
    }),
    revert: useMutation({
      mutationFn: () => api<ImportRecord>('POST', `/imports/${id}/revert`),
      onSuccess: invalidateCatalog,
    }),
    remove: useMutation({
      mutationFn: () => api<void>('DELETE', `/imports/${id}`),
      onSuccess: () => qc.invalidateQueries({ queryKey: ['imports'] }),
    }),
  }
}

export function useTestLlm() {
  return useMutation({
    mutationFn: () =>
      api<{ ok: boolean; model: string; detail: string }>('POST', '/settings/test-llm'),
  })
}
