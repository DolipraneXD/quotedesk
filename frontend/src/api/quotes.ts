import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api } from './client'
import { keys } from './hooks'
import type { Money } from './types'

export type DocLanguage = 'en' | 'zh'
export type QuoteStatus = 'draft' | 'sent' | 'accepted' | 'lost' | 'expired'
export type SectionLayout = 'offer' | 'list'
export type ProformaStatus = 'draft' | 'issued' | 'cancelled'

export const QUOTE_STATUSES: QuoteStatus[] = ['draft', 'sent', 'accepted', 'lost', 'expired']

export interface Customer {
  id: number
  code: string
  name: string
  contact_name: string | null
  email: string | null
  phone: string | null
  address: string | null
  trade_term: string | null
  payment_terms: string | null
  default_margin_pct: Money | null
  notes: string | null
  language: DocLanguage
  created_at: string
}

export type CustomerInput = Partial<Omit<Customer, 'id' | 'created_at'>>

export interface DescriptionLine {
  text: string
  emphasis: boolean
}

export interface LineWarning {
  code: string
  [param: string]: string | number
}

/** A part of a combined product (kind 'config'); only the internal version shows it. */
export interface Component {
  product_id: number | null
  name: string
  qty: number
  cost_usd: Money | null
  condition: 'new' | 'used' | null
  emphasis: boolean
  price_date: string | null
}

/** Send only product_id (and qty) to copy a catalog product into the line. */
export type ComponentInput = Partial<Component> & { qty: number }

export interface QuoteLine {
  id: number
  section_id: number
  sort_order: number
  line_no: string | null
  printed_no: string
  kind: 'product' | 'manual' | 'config'
  product_id: number | null
  category_id: number | null
  /** the saved configuration this combined line was inserted from or saved as */
  configuration_id: number | null
  name: string
  name_emphasis: boolean
  description_lines: DescriptionLine[]
  model_no: string | null
  material: string | null
  image_ids: number[]
  qty: number
  cost_usd: Money | null
  margin_pct: Money | null
  effective_margin_pct: Money | null
  unit_price: Money
  unit_price_manual: boolean
  total: Money
  price_source: { price_date?: string | null; import_id?: number | null }
  components: Component[]
  warnings: LineWarning[]
}

export interface QuoteSection {
  id: number
  title: string | null
  layout: SectionLayout
  sort_order: number
  subtotal: Money
  lines: QuoteLine[]
}

export interface Quote {
  id: number
  offer_no: string
  revision: number
  display_no: string
  parent_quote_id: number | null
  status: QuoteStatus
  offer_date: string
  validity_days: number | null
  valid_until: string | null
  customer_id: number | null
  customer_snapshot: { code?: string; name?: string; [k: string]: unknown }
  contact: string | null
  contact_email: string | null
  trade_term: string | null
  payment_terms: string | null
  currency: string
  language: DocLanguage
  notes_header: string | null
  notes_footer: string | null
  discount_pct: Money | null
  discount_amount: Money | null
  subtotal: Money
  grand_total: Money
  sections: QuoteSection[]
  revisions: { id: number; revision: number; status: QuoteStatus; display_no: string }[]
  proformas: { id: number; pi_no: string; status: ProformaStatus; total: Money }[]
  created_at: string
  updated_at: string
}

export interface QuoteSummary {
  id: number
  display_no: string
  status: QuoteStatus
  offer_date: string
  customer_name: string | null
  customer_code: string | null
  grand_total: Money
  lines: number
  warnings: number
  updated_at: string
}

export type QuotePatch = Partial<
  Pick<
    Quote,
    | 'customer_id'
    | 'status'
    | 'offer_date'
    | 'validity_days'
    | 'contact'
    | 'contact_email'
    | 'trade_term'
    | 'payment_terms'
    | 'language'
    | 'notes_header'
    | 'notes_footer'
    | 'discount_pct'
    | 'discount_amount'
  >
>

export interface LinePatch {
  section_id?: number
  line_no?: string | null
  name?: string
  name_emphasis?: boolean
  description_lines?: DescriptionLine[]
  model_no?: string | null
  material?: string | null
  image_ids?: number[]
  qty?: number
  cost_usd?: Money | null
  margin_pct?: Money | null
  unit_price?: Money | null
  components?: ComponentInput[]
  describe?: boolean
}

export interface ManualLineInput {
  section_id: number
  name: string
  description_lines?: DescriptionLine[]
  model_no?: string | null
  material?: string | null
  cost_usd?: Money | null
  unit_price?: Money | null
  qty: number
  category_id?: number | null
  save_to_catalog?: boolean
}

export interface ProformaLine {
  id: number
  source_line_id: number | null
  sort_order: number
  model_no: string | null
  name: string
  description_lines: DescriptionLine[]
  image_ids: number[]
  qty: number
  unit_price: Money
  total: Money
}

export interface ProformaTerm {
  title: string
  text: string
}

export interface Proforma {
  id: number
  pi_no: string
  quote_id: number | null
  status: ProformaStatus
  po_no: string | null
  issue_date: string
  customer_snapshot: { code?: string; name?: string; [k: string]: unknown }
  attention: string | null
  seller_contact: { name?: string; phone?: string; email?: string }
  currency: string
  foc_pct: Money | null
  freight: Money | null
  terms: ProformaTerm[]
  subtotal: Money
  total: Money
  issued_at: string | null
  revised_from_id: number | null
  lines: ProformaLine[]
  created_at: string
}

export type ProformaSummary = Pick<
  Proforma,
  'id' | 'pi_no' | 'quote_id' | 'status' | 'issue_date' | 'customer_snapshot' | 'total'
>

export type ProformaPatch = Partial<
  Pick<
    Proforma,
    | 'pi_no'
    | 'po_no'
    | 'issue_date'
    | 'attention'
    | 'foc_pct'
    | 'freight'
    | 'terms'
    | 'seller_contact'
    | 'customer_snapshot'
  >
>

export const imageUrl = (id: number) => `/api/v1/images/${id}`
function exportQuery(params: Record<string, boolean>): string {
  const query = Object.keys(params)
    .filter((key) => params[key])
    .map((key) => `${key}=true`)
    .join('&')
  return query ? `?${query}` : ''
}
/** ``internal``: the seller's version with cost, margin and profit, never for the customer. */
export const quotePdfUrl = (id: number, download = false, internal = false) =>
  `/api/v1/quotes/${id}/export.pdf${exportQuery({ download, internal })}`
export const quoteXlsxUrl = (id: number, internal = false) =>
  `/api/v1/quotes/${id}/export.xlsx${exportQuery({ internal })}`
export const proformaPdfUrl = (id: number, download = false) =>
  `/api/v1/proformas/${id}/export.pdf${download ? '?download=true' : ''}`
export const proformaXlsxUrl = (id: number) => `/api/v1/proformas/${id}/export.xlsx`

/** Multipart upload; the backend answers with JSON (ids) or a problem document. */
export async function upload<T>(path: string, field: string, files: File[]): Promise<T> {
  const body = new FormData()
  for (const file of files) body.append(field, file)
  const res = await fetch(`/api/v1${path}`, { method: 'POST', body })
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    throw new ApiError(
      res.status,
      data?.key ?? 'error.unknown',
      data?.detail ?? res.statusText,
      data?.params ?? {},
    )
  }
  return data as T
}

// ---------------------------------------------------------------- customers

const customerKey = ['customers'] as const

export function useCustomers(q?: string) {
  return useQuery({
    queryKey: [...customerKey, q ?? ''],
    queryFn: () => api<Customer[]>('GET', '/customers', { query: { q } }),
    placeholderData: (prev) => prev,
  })
}

export function useSaveCustomer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id?: number; body: CustomerInput }) =>
      id
        ? api<Customer>('PATCH', `/customers/${id}`, { body })
        : api<Customer>('POST', '/customers', { body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: customerKey }),
  })
}

export function useDeleteCustomer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api<void>('DELETE', `/customers/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: customerKey }),
  })
}

// ------------------------------------------------------------------- quotes

export const quotesKey = ['quotes'] as const
const quoteKey = (id: number) => ['quotes', id] as const

export interface QuoteQuery {
  q?: string
  status?: string
  customer?: number
  page?: number
  page_size?: number
}

export function useQuotes(query: QuoteQuery) {
  return useQuery({
    queryKey: [...quotesKey, 'list', query],
    queryFn: () =>
      api<{ items: QuoteSummary[]; total: number }>('GET', '/quotes', { query: { ...query } }),
    placeholderData: (prev) => prev,
  })
}

export function useQuote(id: number) {
  return useQuery({ queryKey: quoteKey(id), queryFn: () => api<Quote>('GET', `/quotes/${id}`) })
}

export function useCreateQuote() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      customer_id?: number | null
      language?: DocLanguage
      layout?: SectionLayout
    }) => api<Quote>('POST', '/quotes', { body }),
    onSuccess: (quote) => {
      qc.setQueryData(quoteKey(quote.id), quote)
      return qc.invalidateQueries({ queryKey: [...quotesKey, 'list'] })
    },
  })
}

/** Every quote mutation answers with the whole quote; it replaces the cached one. */
export function useQuoteActions(id: number) {
  const qc = useQueryClient()
  const store = (quote: Quote) => {
    qc.setQueryData(quoteKey(quote.id), quote)
    void qc.invalidateQueries({ queryKey: [...quotesKey, 'list'] })
  }
  const mutation = <V>(fn: (vars: V) => Promise<Quote>) =>
    // eslint-disable-next-line react-hooks/rules-of-hooks
    useMutation({ mutationFn: fn, onSuccess: store })
  return {
    patch: mutation((body: QuotePatch) => api<Quote>('PATCH', `/quotes/${id}`, { body })),
    addSection: mutation((body: { title?: string; layout?: SectionLayout }) =>
      api<Quote>('POST', `/quotes/${id}/sections`, { body }),
    ),
    patchSection: mutation(
      ({
        sectionId,
        ...body
      }: {
        sectionId: number
        title?: string | null
        layout?: SectionLayout
      }) => api<Quote>('PATCH', `/quotes/${id}/sections/${sectionId}`, { body }),
    ),
    deleteSection: mutation((sectionId: number) =>
      api<Quote>('DELETE', `/quotes/${id}/sections/${sectionId}`),
    ),
    addConfiguration: mutation(
      (body: { section_id: number; configuration_id: number; qty: number }) =>
        api<Quote>('POST', `/quotes/${id}/lines`, { body }),
    ),
    addProduct: mutation((body: { section_id: number; product_id: number; qty: number }) =>
      api<Quote>('POST', `/quotes/${id}/lines`, { body }),
    ),
    addManual: mutation((body: ManualLineInput) =>
      api<Quote>('POST', `/quotes/${id}/lines`, { body }),
    ),
    addCombined: mutation(
      (body: {
        section_id: number
        name: string
        qty: number
        model_no?: string | null
        material?: string | null
      }) => api<Quote>('POST', `/quotes/${id}/lines`, { body: { ...body, kind: 'config' } }),
    ),
    combine: mutation((body: { line_ids: number[]; name: string }) =>
      api<Quote>('POST', `/quotes/${id}/lines/combine`, { body }),
    ),
    split: mutation((lineId: number) => api<Quote>('POST', `/quotes/${id}/lines/${lineId}/split`)),
    patchLine: mutation(({ lineId, ...body }: LinePatch & { lineId: number }) =>
      api<Quote>('PATCH', `/quotes/${id}/lines/${lineId}`, { body }),
    ),
    deleteLine: mutation((lineId: number) => api<Quote>('DELETE', `/quotes/${id}/lines/${lineId}`)),
    reorder: mutation((body: { section_id: number; line_ids: number[] }) =>
      api<Quote>('POST', `/quotes/${id}/lines/reorder`, { body }),
    ),
    refreshCost: mutation((lineId: number) =>
      api<Quote>('POST', `/quotes/${id}/lines/${lineId}/refresh-cost`),
    ),
    duplicate: mutation(() => api<Quote>('POST', `/quotes/${id}/duplicate`)),
    revision: mutation(() => api<Quote>('POST', `/quotes/${id}/revision`)),
  }
}

export function useDeleteQuote() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api<void>('DELETE', `/quotes/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: quotesKey }),
  })
}

// ---------------------------------------------------------------- proformas

const proformaKey = (id: number) => ['proformas', id] as const

export function useProformas(quoteId?: number) {
  return useQuery({
    queryKey: ['proformas', 'list', quoteId ?? null],
    queryFn: () => api<ProformaSummary[]>('GET', '/proformas', { query: { quote: quoteId } }),
  })
}

export function useProforma(id: number) {
  return useQuery({
    queryKey: proformaKey(id),
    queryFn: () => api<Proforma>('GET', `/proformas/${id}`),
  })
}

export function useCreateProforma(quoteId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { line_ids: number[]; po_no?: string | null }) =>
      api<Proforma>('POST', `/quotes/${quoteId}/proforma`, { body }),
    onSuccess: (pi) => {
      qc.setQueryData(proformaKey(pi.id), pi)
      void qc.invalidateQueries({ queryKey: quoteKey(quoteId) })
      return qc.invalidateQueries({ queryKey: ['proformas', 'list'] })
    },
  })
}

export function useProformaActions(id: number) {
  const qc = useQueryClient()
  const store = (pi: Proforma) => {
    qc.setQueryData(proformaKey(pi.id), pi)
    void qc.invalidateQueries({ queryKey: ['proformas', 'list'] })
    if (pi.quote_id) void qc.invalidateQueries({ queryKey: quoteKey(pi.quote_id) })
  }
  const mutation = <V>(fn: (vars: V) => Promise<Proforma>) =>
    // eslint-disable-next-line react-hooks/rules-of-hooks
    useMutation({ mutationFn: fn, onSuccess: store })
  return {
    patch: mutation((body: ProformaPatch) => api<Proforma>('PATCH', `/proformas/${id}`, { body })),
    patchLine: mutation(
      ({ lineId, ...body }: Partial<Omit<ProformaLine, 'id'>> & { lineId: number }) =>
        api<Proforma>('PATCH', `/proformas/${id}/lines/${lineId}`, { body }),
    ),
    deleteLine: mutation((lineId: number) =>
      api<Proforma>('DELETE', `/proformas/${id}/lines/${lineId}`),
    ),
    issue: mutation(() => api<Proforma>('POST', `/proformas/${id}/issue`)),
    cancel: mutation(() => api<Proforma>('POST', `/proformas/${id}/cancel`)),
    revise: mutation(() => api<Proforma>('POST', `/proformas/${id}/revise`)),
    remove: useMutation({
      mutationFn: () => api<void>('DELETE', `/proformas/${id}`),
      onSuccess: () => qc.invalidateQueries({ queryKey: ['proformas'] }),
    }),
  }
}

// ------------------------------------------------------------------ images

export function useProductImages(productId: number) {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: keys.product(productId) })
  return {
    add: useMutation({
      mutationFn: (files: File[]) =>
        upload<number[]>(`/products/${productId}/images`, 'files', files),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (imageId: number) =>
        api<number[]>('DELETE', `/products/${productId}/images/${imageId}`),
      onSuccess: refresh,
    }),
  }
}

export function useCompanyImage(kind: 'logo' | 'signature') {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: keys.settings })
  return {
    set: useMutation({
      mutationFn: (file: File) => upload<number>(`/settings/images/${kind}`, 'file', [file]),
      onSuccess: refresh,
    }),
    clear: useMutation({
      mutationFn: () => api<void>('DELETE', `/settings/images/${kind}`),
      onSuccess: refresh,
    }),
  }
}
