import { Input, InputNumber } from 'antd'
import { useState } from 'react'

import { trim } from '../../lib/money'

/** A text input that saves on blur or Enter, only when the value changed. */
export function CommitText({
  value,
  onCommit,
  disabled,
  placeholder,
  style,
}: {
  value: string | null
  onCommit: (value: string | null) => void
  disabled?: boolean
  placeholder?: string
  style?: React.CSSProperties
}) {
  const [draft, setDraft] = useState(value ?? '')
  // a new value from the server replaces the draft (React's "adjust state on prop change")
  const [seen, setSeen] = useState(value)
  if (value !== seen) {
    setSeen(value)
    setDraft(value ?? '')
  }
  const commit = () => {
    const next = draft.trim() === '' ? null : draft
    if (next !== (value ?? null)) onCommit(next)
  }
  return (
    <Input
      value={draft}
      disabled={disabled}
      placeholder={placeholder}
      style={style}
      size="small"
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onPressEnter={commit}
    />
  )
}

/** A decimal input (string mode, no floats) that saves on blur or Enter. */
export function CommitNumber({
  value,
  onCommit,
  disabled,
  placeholder,
  min,
  precision,
  addonAfter,
  width = 96,
  integer,
}: {
  value: string | number | null
  onCommit: (value: string | null) => void
  disabled?: boolean
  placeholder?: string
  min?: string
  precision?: number
  addonAfter?: string
  width?: number
  integer?: boolean
}) {
  const normalize = (v: string | number | null) => (v === null || v === '' ? null : trim(String(v)))
  const [draft, setDraft] = useState<string | null>(normalize(value))
  const [seen, setSeen] = useState(value)
  if (value !== seen) {
    setSeen(value)
    setDraft(normalize(value))
  }
  const commit = () => {
    if (draft !== normalize(value)) onCommit(draft)
  }
  return (
    <InputNumber<string>
      stringMode
      size="small"
      value={draft ?? undefined}
      min={min}
      precision={integer ? 0 : precision}
      disabled={disabled}
      placeholder={placeholder}
      addonAfter={addonAfter}
      style={{ width }}
      onChange={(v) => setDraft(v === null || v === '' ? null : String(v))}
      onBlur={commit}
      onPressEnter={commit}
    />
  )
}
