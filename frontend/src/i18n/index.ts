import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from './en.json'
import zh from './zh.json'

export type Lang = 'en' | 'zh'

const STORAGE_KEY = 'quotedesk.lang'

function initialLang(): Lang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'en' || stored === 'zh') return stored
  } catch {
    // storage unavailable: fall through to the default
  }
  return 'zh'
}

export function rememberLang(lang: Lang) {
  try {
    localStorage.setItem(STORAGE_KEY, lang)
  } catch {
    // per-browser convenience only; the server-side setting is the source of truth
  }
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, zh: { translation: zh } },
  lng: initialLang(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

export default i18n
