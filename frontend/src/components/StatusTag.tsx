import {
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  ExperimentOutlined,
  QuestionCircleOutlined,
  StarOutlined,
} from '@ant-design/icons'
import { Space, Tag, Tooltip } from 'antd'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { Product, ProductFlag, ProductStatus } from '../api/types'

const STATUS_COLORS: Record<ProductStatus, string> = {
  active: 'green',
  discontinued: 'red',
  stock_only: 'orange',
  no_supply: 'volcano',
  inactive: 'default',
}

const FLAG_ICONS: Record<ProductFlag, ReactNode> = {
  confirm_before_order: <ExclamationCircleOutlined style={{ color: '#d48806' }} />,
  lead_time_confirm: <ClockCircleOutlined style={{ color: '#d48806' }} />,
  needs_validation: <ExperimentOutlined style={{ color: '#cf1322' }} />,
  quote_on_request: <QuestionCircleOutlined style={{ color: '#1f4e8c' }} />,
  recommended: <StarOutlined style={{ color: '#389e0d' }} />,
}

export function StatusTag({ status }: { status: ProductStatus }) {
  const { t } = useTranslation()
  return <Tag color={STATUS_COLORS[status]}>{t(`status.${status}`)}</Tag>
}

export function FlagIcons({ product }: { product: Product }) {
  const { t } = useTranslation()
  const flags = (Object.keys(FLAG_ICONS) as ProductFlag[]).filter((f) => product[f])
  if (!flags.length) return null
  return (
    <Space size={4}>
      {flags.map((f) => (
        <Tooltip key={f} title={t(`flags.${f}`)}>
          {FLAG_ICONS[f]}
        </Tooltip>
      ))}
    </Space>
  )
}
