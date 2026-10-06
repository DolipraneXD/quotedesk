import { Select, Space } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useProducts } from '../api/hooks'
import type { DeviceType } from '../api/types'
import { formatCost } from '../lib/money'
import { useDebounced } from '../lib/useDebounced'
import { DeviceSelect } from './DeviceSelect'

/**
 * Searchable product select backed by the full-text search endpoint. With ``deviceFilter``
 * a device select sits in front of it: picking PC hides tablet and laptop parts (general
 * parts, with no device, always show). ``device`` is its starting value (a build's device).
 */
export default function ProductPicker({
  value,
  onChange,
  excludeId,
  categoryId,
  deviceFilter = false,
  device,
}: {
  value?: number
  onChange?: (id: number) => void
  excludeId?: number
  categoryId?: number
  deviceFilter?: boolean
  device?: DeviceType | null
}) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const [only, setOnly] = useState<DeviceType | null>(device ?? null)
  // the build's device changed (saved in its details): start from it again
  const [startedFrom, setStartedFrom] = useState(device ?? null)
  if ((device ?? null) !== startedFrom) {
    setStartedFrom(device ?? null)
    setOnly(device ?? null)
  }
  const q = useDebounced(search, 250)
  const products = useProducts({
    q,
    category: categoryId,
    device: deviceFilter && only ? only : undefined,
    page_size: 30,
  })
  const options = (products.data?.items ?? [])
    .filter((p) => p.id !== excludeId)
    .map((p) => ({
      value: p.id,
      label: (
        <span>
          {p.name_zh}
          {p.device_type && <span className="qd-muted"> · {t(`device.${p.device_type}`)}</span>}
          {p.erp_code && <span className="qd-muted"> · {p.erp_code}</span>}
          {p.current_price_usd && (
            <span className="qd-muted"> · {formatCost(p.current_price_usd)}</span>
          )}
        </span>
      ),
    }))
  const select = (
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
  if (!deviceFilter) return select
  return (
    <Space.Compact style={{ width: '100%' }}>
      <DeviceSelect
        value={only}
        onChange={setOnly}
        placeholder={t('device.all')}
        style={{ width: 150, flex: 'none' }}
      />
      {select}
    </Space.Compact>
  )
}
