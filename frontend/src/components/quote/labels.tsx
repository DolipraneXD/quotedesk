import { Tag } from 'antd'
import { useTranslation } from 'react-i18next'

import type { LineWarning, ProformaStatus, QuoteStatus } from '../../api/quotes'
import { formatCost } from '../../lib/money'

const QUOTE_COLORS: Record<QuoteStatus, string> = {
  draft: 'default',
  sent: 'blue',
  accepted: 'green',
  lost: 'red',
  expired: 'orange',
}

const PROFORMA_COLORS: Record<ProformaStatus, string> = {
  draft: 'default',
  issued: 'green',
  cancelled: 'red',
}

export function QuoteStatusTag({ status }: { status: QuoteStatus }) {
  const { t } = useTranslation()
  return <Tag color={QUOTE_COLORS[status]}>{t(`quote.statuses.${status}`)}</Tag>
}

export function ProformaStatusTag({ status }: { status: ProformaStatus }) {
  const { t } = useTranslation()
  return <Tag color={PROFORMA_COLORS[status]}>{t(`proforma.statuses.${status}`)}</Tag>
}

/** "Discontinued", "Price changed: $420 (was $400)", …; a part's warning starts with its name. */
export function WarningText({ warning }: { warning: LineWarning }) {
  const { t } = useTranslation()
  const part = warning.part ? `${warning.part}: ` : ''
  if (warning.code === 'status') {
    return (
      <>
        {part}
        {t(`status.${warning.status}`)}
      </>
    )
  }
  return (
    <>
      {part}
      {t(`quote.warnings.${warning.code}`, {
        ...warning,
        now: formatCost(String(warning.now ?? '')),
        was: formatCost(String(warning.was ?? '')),
      })}
    </>
  )
}
