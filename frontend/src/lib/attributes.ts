import type { AttributeField, Category, Product } from '../api/types'
import { attrLabel } from './i18n-helpers'

export function formatAttrValue(
  field: AttributeField | undefined,
  value: unknown,
  t: (k: string) => string,
) {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'boolean') return value ? t('common.yes') : t('common.no')
  // "8" -> "8 GB", but source spellings that carry their own unit ("1T", "128G") stay as-is
  const numeric = /^-?\d+(\.\d+)?$/.test(String(value).trim())
  return field?.unit && numeric ? `${value} ${field.unit}` : String(value)
}

/** Short one-line summary of the identifying attributes, e.g. "DDR4 · 8 GB · 2666 MHz". */
export function attributeSummary(
  product: Product,
  category: Category | undefined,
  t: (k: string) => string,
) {
  const schema = category?.attribute_schema ?? []
  const fields = schema.filter((f) => f.in_fingerprint)
  return fields
    .map((f) => formatAttrValue(f, product.attributes[f.key], t))
    .filter(Boolean)
    .join(' · ')
}

/** All attributes in schema order, then any extra keys the source carried. */
export function attributeRows(
  product: Product,
  category: Category | undefined,
  lang: string,
  t: (k: string) => string,
) {
  const schema = category?.attribute_schema ?? []
  const known = new Set(schema.map((f) => f.key))
  const rows = schema
    .filter((f) => product.attributes[f.key] !== undefined)
    .map((f) => ({
      key: f.key,
      label: attrLabel(f, lang),
      value: formatAttrValue(f, product.attributes[f.key], t),
      inFingerprint: f.in_fingerprint,
    }))
  for (const [key, value] of Object.entries(product.attributes)) {
    if (!known.has(key)) {
      rows.push({
        key,
        label: key,
        value: formatAttrValue(undefined, value, t),
        inFingerprint: false,
      })
    }
  }
  return rows
}
