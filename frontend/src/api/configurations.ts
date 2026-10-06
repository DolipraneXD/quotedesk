import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import { quotesKey, upload, type DescriptionLine, type QuoteStatus } from './quotes'
import type { DeviceType, Money } from './types'

export type Condition = 'new' | 'used'

export interface ConfigurationItem {
  id: number
  product_id: number | null
  name: string
  qty: number
  condition: Condition | null
  emphasis: boolean
  cost_usd: Money | null
  /** what the part costs now: the catalog price, or its own cost when typed by hand */
  unit_cost: Money | null
  product_name: string | null
  product_status: string | null
  price_date: string | null
}

export interface ConfigurationItemInput {
  product_id?: number | null
  name?: string | null
  cost_usd?: Money | null
  qty: number
  condition?: Condition | null
  emphasis?: boolean
}

export interface Configuration {
  id: number
  name: string
  name_zh: string | null
  notes: string | null
  platform: string | null
  device_type: DeviceType | null
  model_no: string | null
  material: string | null
  base_margin_pct: Money | null
  image_ids: number[]
  items: ConfigurationItem[]
  description_lines: DescriptionLine[]
  unit_cost: Money | null
  saved_cost: Money | null
  cost_changed: boolean
  missing_cost: number
  used_in: number
  updated_at: string
}

export interface ConfigurationSummary {
  id: number
  name: string
  name_zh: string | null
  platform: string | null
  device_type: DeviceType | null
  model_no: string | null
  parts: number
  unit_cost: Money | null
  saved_cost: Money | null
  cost_changed: boolean
  missing_cost: number
  used_in: number
  image_id: number | null
  updated_at: string
}

export interface ConfigurationUsage {
  quote_id: number
  display_no: string
  status: QuoteStatus
  offer_date: string
  customer_name: string | null
  line_id: number
  qty: number
  unit_price: Money
}

export type ConfigurationPatch = Partial<
  Pick<
    Configuration,
    | 'name'
    | 'name_zh'
    | 'notes'
    | 'platform'
    | 'device_type'
    | 'model_no'
    | 'material'
    | 'base_margin_pct'
  >
> & { items?: ConfigurationItemInput[] }

const configsKey = ['configurations'] as const
const configKey = (id: number) => ['configurations', id] as const

/** Turns a saved part back into what the API accepts, keeping its values. */
export const itemInput = (item: ConfigurationItem): ConfigurationItemInput => ({
  product_id: item.product_id,
  name: item.name,
  cost_usd: item.product_id ? null : item.cost_usd,
  qty: item.qty,
  condition: item.condition,
  emphasis: item.emphasis,
})

export function useConfigurations(q?: string) {
  return useQuery({
    queryKey: [...configsKey, 'list', q ?? ''],
    queryFn: () => api<ConfigurationSummary[]>('GET', '/configurations', { query: { q } }),
  })
}

export function useConfiguration(id: number) {
  return useQuery({
    queryKey: configKey(id),
    queryFn: () => api<Configuration>('GET', `/configurations/${id}`),
    enabled: id > 0,
  })
}

export function useConfigurationUsage(id: number) {
  return useQuery({
    queryKey: [...configKey(id), 'usage'],
    queryFn: () => api<ConfigurationUsage[]>('GET', `/configurations/${id}/usage`),
    enabled: id > 0,
  })
}

/** Every change answers with the whole configuration; it replaces the cached one. */
export function useConfigurationActions(id: number) {
  const qc = useQueryClient()
  const store = (config: Configuration) => {
    qc.setQueryData(configKey(config.id), config)
    void qc.invalidateQueries({ queryKey: [...configsKey, 'list'] })
  }
  return {
    patch: useMutation({
      mutationFn: (body: ConfigurationPatch) =>
        api<Configuration>('PATCH', `/configurations/${id}`, { body }),
      onSuccess: store,
    }),
    duplicate: useMutation({
      mutationFn: () => api<Configuration>('POST', `/configurations/${id}/duplicate`),
      onSuccess: store,
    }),
    remove: useMutation({
      mutationFn: () => api<void>('DELETE', `/configurations/${id}`),
      onSuccess: () => qc.invalidateQueries({ queryKey: configsKey }),
    }),
    addImages: useMutation({
      mutationFn: (files: File[]) =>
        upload<Configuration>(`/configurations/${id}/images`, 'files', files),
      onSuccess: store,
    }),
    removeImage: useMutation({
      mutationFn: (imageId: number) =>
        api<Configuration>('DELETE', `/configurations/${id}/images/${imageId}`),
      onSuccess: store,
    }),
  }
}

export function useCreateConfiguration() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ConfigurationPatch & { name: string }) =>
      api<Configuration>('POST', '/configurations', { body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: configsKey }),
  })
}

/** Keep a combined product built in a quote; the quote line is linked to it. */
export function useSaveLineAsConfiguration() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { quote_id: number; line_id: number; name?: string }) =>
      api<Configuration>('POST', '/configurations/from-line', { body }),
    onSuccess: (_config, body) => {
      void qc.invalidateQueries({ queryKey: configsKey })
      void qc.invalidateQueries({ queryKey: [...quotesKey, body.quote_id] })
    },
  })
}
