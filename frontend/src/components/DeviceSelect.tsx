import { Select } from 'antd'
import { useTranslation } from 'react-i18next'

import type { DeviceType } from '../api/types'
import { DEVICE_TYPES } from '../lib/devices'

/** What a part or build is for; empty = general (a part that fits any device). */
export function DeviceSelect({
  value,
  onChange,
  placeholder,
  style,
}: {
  value?: DeviceType | null
  onChange?: (value: DeviceType | null) => void
  placeholder?: string
  style?: React.CSSProperties
}) {
  const { t } = useTranslation()
  return (
    <Select<DeviceType>
      allowClear
      value={value ?? undefined}
      onChange={(v) => onChange?.(v ?? null)}
      placeholder={placeholder ?? t('device.general')}
      options={DEVICE_TYPES.map((d) => ({ value: d, label: t(`device.${d}`) }))}
      style={style}
    />
  )
}
