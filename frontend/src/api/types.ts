// Mirrors backend/app/schemas. Money and decimals arrive as strings, never numbers.

export type Money = string

export interface AttributeField {
  key: string
  label_en: string
  label_zh: string
  type: AttributeType
  unit?: string | null
  options?: string[] | null
  in_fingerprint: boolean
}

export type AttributeType =
  | 'text'
  | 'number'
  | 'int'
  | 'capacity'
  | 'frequency'
  | 'form_factor'
  | 'interface'
  | 'brand'
  | 'bool'

export interface Category {
  id: number
  code: string
  name_en: string
  name_zh: string
  is_main: boolean
  attribute_schema: AttributeField[]
  default_margin_pct: Money | null
  sort_order: number
  product_count: number
}

export interface BrandAlias {
  id: number
  alias: string
  lang: string
}

export interface Brand {
  id: number
  canonical: string
  name_en: string | null
  name_zh: string | null
  needs_review: boolean
  aliases: BrandAlias[]
  product_count: number
}

export const PRODUCT_STATUSES = [
  'active',
  'discontinued',
  'stock_only',
  'no_supply',
  'inactive',
] as const
export type ProductStatus = (typeof PRODUCT_STATUSES)[number]

export const PRODUCT_FLAGS = [
  'confirm_before_order',
  'lead_time_confirm',
  'needs_validation',
  'quote_on_request',
  'recommended',
] as const
export type ProductFlag = (typeof PRODUCT_FLAGS)[number]

/** The import a product came from (see ProductSource). */
export interface ImportRef {
  id: number
  filename: string
  status: string
  committed_at: string | null
}

export interface Product {
  id: number
  category_id: number
  erp_code: string | null
  erp_code_alt: string[]
  mpn: string | null
  name_zh: string
  name_en: string | null
  name_en_auto: boolean
  brand_id: number | null
  brand: { id: number; canonical: string; name_zh: string | null } | null
  attributes: Record<string, string | number | boolean>
  fingerprint: string
  current_price_usd: Money | null
  current_price_tier_forecast_usd: Money | null
  price_date: string | null
  last_import_id: number | null
  created_import_id: number | null
  created_import: ImportRef | null
  last_import: ImportRef | null
  status: ProductStatus
  confirm_before_order: boolean
  lead_time_confirm: boolean
  needs_validation: boolean
  quote_on_request: boolean
  recommended: boolean
  stock_qty: number | null
  demand_qty: number | null
  stock_after_qty: number | null
  max_order_qty: number | null
  from_stock_qty: number | null
  payment_terms: string | null
  supply_note: string | null
  market: string | null
  notes_raw: string | null
  platform: string | null
  is_manual: boolean
  description_zh: string | null
  description_en: string | null
  model_no: string | null
  material: string | null
  image_ids: number[]
  created_at: string
  updated_at: string
}

export interface ProductList {
  items: Product[]
  total: number
  page: number
  page_size: number
}

export interface ProductQuery {
  q?: string
  category?: number
  brand?: number
  status?: string
  page?: number
  page_size?: number
  sort?: 'name' | 'price' | 'updated' | 'created' | 'price_date'
  order?: 'asc' | 'desc'
}

export type ProductInput = Partial<
  Omit<
    Product,
    | 'id'
    | 'brand'
    | 'fingerprint'
    | 'current_price_usd'
    | 'current_price_tier_forecast_usd'
    | 'price_date'
    | 'last_import_id'
    | 'created_at'
    | 'updated_at'
    | 'name_en_auto'
  >
> & { price_usd?: Money | null; price_date?: string | null }

export interface PriceRow {
  id: number
  import_id: number | null
  price_usd: Money
  tier: 'standard' | 'forecast'
  amount_original: Money | null
  currency_original: string | null
  fx_rate: Money | null
  price_date: string | null
  source_ref: string | null
  note: string | null
  is_current: boolean
  created_at: string
}

export interface ProductAlias {
  id: number
  fingerprint: string
  name_zh: string | null
  created_at: string
}

export interface NoteRule {
  id: number
  pattern: string
  field: string
  kind: string
  value: string | null
  sort_order: number
  enabled: boolean
}

export interface CompanySettings {
  name_en: string
  name_zh: string
  address_en: string
  address_zh: string
  logo_image_id: number | null
  phone: string
  email: string
  bank_account_name: string
  bank_account_no: string
  bank_name: string
  bank_swift: string
  seller_name: string
  seller_phone: string
  seller_email: string
  signature_image_id: number | null
}

export interface Settings {
  company: CompanySettings
  offer_prefix: string
  pi_prefix: string
  pi_payment_term: string
  pi_lead_time: string
  pi_delivery_place: string
  pi_warranty: string
  price_age_warning_days: number
  default_margin_pct: Money
  default_fx_rate_cny_usd: Money
  default_validity_days: number
  llm_provider: LlmProvider
  llm_model: string
  gemini_model: string
  groq_model: string
  ui_language: 'en' | 'zh'
  rounding: number
  backup_retention: number
  anthropic_api_key_set: boolean
  gemini_api_key_set: boolean
  groq_api_key_set: boolean
}

export type LlmProvider = 'anthropic' | 'google' | 'groq'

/** Write-only key fields: undefined = keep, '' = remove. */
export interface ApiKeysIn {
  anthropic_api_key?: string | null
  gemini_api_key?: string | null
  groq_api_key?: string | null
}

export function providerKeySet(settings: Settings): boolean {
  return {
    anthropic: settings.anthropic_api_key_set,
    google: settings.gemini_api_key_set,
    groq: settings.groq_api_key_set,
  }[settings.llm_provider]
}

export interface Dashboard {
  products: number
  products_by_status: Record<string, number>
  products_by_category: { category_id: number; count: number }[]
  products_without_price: number
  categories: number
  brands: number
  last_import: {
    id: number
    filename: string
    committed_at: string
    new: number
    updated: number
    unchanged: number
  } | null
  price_moves: { product_id: number; name: string | null; old: Money; new: Money; pct: string }[]
  open_quotes: {
    count: number
    value: Money
    recent: {
      id: number
      display_no: string
      status: string
      customer_name: string | null
      grand_total: Money
      updated_at: string
    }[]
  }
  /** lines of open quotes whose product changed price or stopped being sold */
  quote_alerts: ({
    quote_id: number
    display_no: string
    customer_name: string | null
    line: string
    code: string
  } & Record<string, string | number | null>)[]
  old_prices: {
    days: number
    count: number
    oldest: { product_id: number; name: string; price_date: string }[]
  }
}
