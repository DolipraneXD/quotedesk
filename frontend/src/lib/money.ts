// Money arrives from the API as decimal strings. Formatting works on the digits
// directly (BigInt), so no price ever passes through a binary float.

const SCALE = 4

function toScaled(value: string): bigint | null {
  const m = /^\s*(-?)(\d*)(?:\.(\d*))?\s*$/.exec(value)
  if (!m || (m[2] === '' && !m[3])) return null
  const frac = (m[3] ?? '').padEnd(SCALE + 1, '0')
  let scaled = BigInt((m[2] || '0') + frac.slice(0, SCALE))
  if (Number(frac[SCALE]) >= 5) scaled += 1n // half-up on the 5th decimal
  return m[1] === '-' ? -scaled : scaled
}

/** Round half-up to `decimals` places and render with thousands separators. */
export function formatDecimal(value: string | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || value === '') return ''
  const scaled = toScaled(value)
  if (scaled === null) return value
  const negative = scaled < 0n
  const abs = negative ? -scaled : scaled
  const drop = 10n ** BigInt(SCALE - decimals)
  const rounded = (abs + drop / 2n) / drop
  const unit = 10n ** BigInt(decimals)
  const intPart = (rounded / unit).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const fracPart = decimals > 0 ? '.' + (rounded % unit).toString().padStart(decimals, '0') : ''
  return (negative ? '-' : '') + intPart + fracPart
}

/** Sell prices: always 2 decimals. */
export function formatUsd(value: string | null | undefined): string {
  const text = formatDecimal(value, 2)
  return text ? `$ ${text}` : ''
}

/**
 * Cost prices from supplier lists: 2 to 4 decimals, because cheap components are
 * quoted to the tenth of a cent ($ 1.9563, $ 0.4125) and rounding would hide that.
 */
export function formatCost(value: string | null | undefined): string {
  const text = formatDecimal(value, 4)
  if (!text) return ''
  const [int, frac = ''] = text.split('.')
  const trimmed = frac.replace(/0+$/, '').padEnd(2, '0')
  return `$ ${int}.${trimmed}`
}

/** Compare two decimal strings: -1, 0 or 1. */
export function compareDecimal(a: string, b: string): number {
  const x = toScaled(a) ?? 0n
  const y = toScaled(b) ?? 0n
  return x === y ? 0 : x < y ? -1 : 1
}

/** "400.0000" -> "400", "0.3330" -> "0.333": a decimal string for editing. */
export function trim(value: string): string {
  return value.includes('.') ? value.replace(/\.?0+$/, '') : value
}
