import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import type { ImportRef } from '../api/types'
import { formatDateTime } from '../lib/datetime'

/** "from <file>" linking to the import, or "Entered by hand". */
export function ImportSource({ source }: { source: ImportRef | null }) {
  const { t } = useTranslation()
  if (!source) return <span>{t('product.addedManual')}</span>
  return (
    <span>
      {t('product.addedFrom')}{' '}
      <Link to={`/imports/${source.id}`} title={source.filename}>
        {source.filename}
      </Link>
      {source.status === 'reverted' && ` (${t('imports.status.reverted')})`}
    </span>
  )
}

/** When the product was added and by what: shown in the list and on the product page. */
export default function ProductAdded({
  createdAt,
  source,
}: {
  createdAt: string
  source: ImportRef | null
}) {
  return (
    <div>
      <div>{formatDateTime(createdAt)}</div>
      <div className="qd-muted qd-ellipsis">
        <ImportSource source={source} />
      </div>
    </div>
  )
}
