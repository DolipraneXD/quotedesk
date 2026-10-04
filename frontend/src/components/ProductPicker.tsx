import { Select } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useProducts } from '../api/hooks'
import { formatCost } from '../lib/money'
import { useDebounced } from '../lib/useDebounced'

/** Searchable product select backed by the full-text search endpoint. */
export default function ProductPicker({
  value,
  onChange,
  excludeId,
  categoryId,
}: {
  value?: number
  onChange?: (id: number) => void
  excludeId?: number
  categoryId?: number
}) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const q = useDebounced(search, 250)
  const products = useProducts({ q, category: categoryId, page_size: 30 })
  const options = (products.data?.items ?? [])
    .filter((p) => p.id !== excludeId)
    .map((p) => ({
      value: p.id,
      label: (
        <span>
          {p.name_zh}
          {p.erp_code && <span className="qd-muted"> · {p.erp_code}</span>}
          {p.current_price_usd && (
            <span className="qd-muted"> · {formatCost(p.current_price_usd)}</span>
          )}
        </span>
      ),
    }))
  return (
    <Select
      showSearch
      value={value}
      onChange={onChange}
      filterOption={false}
      onSearch={setSearch}
      options={options}
      loading={products.isFetching}
      placeholder={t('product.searchPlaceholder')}
      style={{ width: '100%' }}
      notFoundContent={t('common.noResults')}
    />
  )
}
