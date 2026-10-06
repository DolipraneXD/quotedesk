import { useTranslation } from 'react-i18next'

import type { PriceRow } from '../api/types'
import { formatDecimal } from '../lib/money'
import { useWidth } from '../lib/useWidth'

const H = 220
const PAD = { top: 16, right: 24, bottom: 28, left: 56 }

/**
 * Standard-tier price over price date. Plotting needs coordinates, so prices become
 * numbers here for drawing only; every label is rendered from the decimal string.
 */
export default function PriceChart({ rows }: { rows: PriceRow[] }) {
  const { t } = useTranslation()
  const [ref, width] = useWidth<HTMLDivElement>()
  const points = rows
    .filter((r) => r.tier === 'standard')
    .slice()
    .sort(
      (a, b) =>
        (a.price_date ?? '').localeCompare(b.price_date ?? '') ||
        a.created_at.localeCompare(b.created_at),
    )

  return (
    <div ref={ref}>
      {points.length < 2 ? (
        <div className="qd-muted">{t('product.chartNeedsTwo')}</div>
      ) : (
        <Plot points={points} width={width} label={t('product.priceHistory')} />
      )}
    </div>
  )
}

function Plot({ points, width: W, label }: { points: PriceRow[]; width: number; label: string }) {
  const values = points.map((p) => Number(p.price_usd))
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || max || 1
  const lo = Math.max(0, min - span * 0.1)
  const hi = max + span * 0.1
  const x = (i: number) => PAD.left + (i * (W - PAD.left - PAD.right)) / (points.length - 1)
  const y = (v: number) => PAD.top + (1 - (v - lo) / (hi - lo)) * (H - PAD.top - PAD.bottom)
  const path = values
    .map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`)
    .join(' ')
  const ticks = [lo, (lo + hi) / 2, hi]
  const labelEvery = Math.max(1, Math.ceil(points.length / Math.floor(W / 70)))

  return (
    <svg
      className="qd-price-chart"
      viewBox={`0 0 ${W} ${H}`}
      width={W}
      height={H}
      role="img"
      aria-label={label}
    >
      {ticks.map((v) => (
        <g key={v}>
          <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} />
          <text x={PAD.left - 8} y={y(v) + 4} textAnchor="end">
            {formatDecimal(v.toFixed(4), 2)}
          </text>
        </g>
      ))}
      <path className="line" d={path} />
      {points.map((p, i) => (
        <g key={p.id}>
          <circle cx={x(i)} cy={y(values[i])} r={3.5}>
            <title>{`${p.price_date ?? ''}  $ ${formatDecimal(p.price_usd)}`}</title>
          </circle>
          {(i % labelEvery === 0 || i === points.length - 1) && (
            <text x={x(i)} y={H - 8} textAnchor="middle">
              {p.price_date?.slice(5) ?? ''}
            </text>
          )}
        </g>
      ))}
    </svg>
  )
}
