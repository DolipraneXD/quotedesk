import type { TFunction } from 'i18next'

import { ApiError } from '../api/client'

type Named = { name_en?: string | null; name_zh?: string | null }

/** Pick the name for the UI language, falling back to the other one. */
export function localName(item: Named | null | undefined, lang: string): string {
  if (!item) return ''
  return (lang === 'en' ? item.name_en || item.name_zh : item.name_zh || item.name_en) ?? ''
}

export function attrLabel(field: { label_en: string; label_zh: string }, lang: string): string {
  return lang === 'en' ? field.label_en : field.label_zh
}

/** Translate an API problem by its key; fall back to the server's English detail. */
export function errorMessage(t: TFunction, err: unknown): string {
  if (err instanceof ApiError) {
    const key = `errors.${err.key}`
    const translated = t(key, err.params as Record<string, string>)
    return translated === key ? err.message : translated
  }
  return err instanceof Error ? err.message : String(err)
}
