import { DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { Button, Checkbox, Input, InputNumber, Select, Space, Table, Typography } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import type { Component, ComponentInput, QuoteLine } from '../../api/quotes'
import { formatCost, trim } from '../../lib/money'
import ProductPicker from '../ProductPicker'
import { CommitNumber, CommitText } from './CommitInput'

/** The parts of a combined product. Every change sends the whole list back; parts keep
 *  the values they were copied with, new catalog parts are copied by the server. */
export default function ComponentsEditor({
  line,
  readOnly,
  onSave,
  onDescribe,
}: {
  line: QuoteLine
  readOnly: boolean
  onSave: (components: ComponentInput[]) => Promise<unknown>
  onDescribe: () => Promise<unknown>
}) {
  const { t } = useTranslation()
  const [productId, setProductId] = useState<number | undefined>()
  const [qty, setQty] = useState(1)
  const [name, setName] = useState('')
  const [cost, setCost] = useState<string | null>(null)

  const parts = line.components
  const replace = (index: number, change: Partial<Component>) =>
    onSave(parts.map((c, i) => (i === index ? { ...c, ...change } : c)))

  const addProduct = async () => {
    if (!productId) return
    await onSave([...parts, { product_id: productId, qty }])
    setProductId(undefined)
    setQty(1)
  }
  const addByHand = async () => {
    if (!name.trim()) return
    await onSave([...parts, { name: name.trim(), qty, cost_usd: cost }])
    setName('')
    setCost(null)
    setQty(1)
  }

  return (
    <div className="qd-parts">
      <Space style={{ marginBottom: 8 }} wrap>
        <Typography.Text strong>{t('quote.parts')}</Typography.Text>
        <Typography.Text type="secondary">
          {t('quote.unitCostFromParts')}: {formatCost(line.cost_usd) || '—'}
        </Typography.Text>
        {!readOnly && (
          <Button size="small" icon={<ReloadOutlined />} onClick={() => void onDescribe()}>
            {t('quote.rebuildDescription')}
          </Button>
        )}
      </Space>
      <Table<Component>
        rowKey={(_, i) => String(i)}
        size="small"
        pagination={false}
        dataSource={parts}
        locale={{ emptyText: t('quote.noParts') }}
        columns={[
          {
            title: t('quote.part'),
            key: 'name',
            render: (_, c, i) => (
              <Space size={4}>
                <CommitText
                  value={c.name}
                  disabled={readOnly}
                  style={{ width: 300 }}
                  onCommit={(v) => v && void replace(i, { name: v })}
                />
                {c.product_id && (
                  <Link to={`/products/${c.product_id}`} className="qd-muted">
                    #{c.product_id}
                  </Link>
                )}
              </Space>
            ),
          },
          {
            title: t('config.red'),
            key: 'red',
            width: 60,
            align: 'center',
            render: (_, c, i) => (
              <Checkbox
                checked={c.emphasis}
                disabled={readOnly}
                onChange={(e) => void replace(i, { emphasis: e.target.checked })}
              />
            ),
          },
          {
            title: t('quote.condition'),
            key: 'condition',
            width: 140,
            render: (_, c, i) => (
              <Select
                size="small"
                allowClear
                disabled={readOnly}
                value={c.condition ?? undefined}
                placeholder="—"
                style={{ width: 128 }}
                onChange={(v) => void replace(i, { condition: v ?? null })}
                options={(['new', 'used'] as const).map((v) => ({
                  value: v,
                  label: t(`quote.conditions.${v}`),
                }))}
              />
            ),
          },
          {
            title: t('quote.perUnit'),
            key: 'qty',
            width: 100,
            align: 'right',
            render: (_, c, i) => (
              <CommitNumber
                value={c.qty}
                integer
                min="1"
                width={84}
                disabled={readOnly}
                onCommit={(v) => v && void replace(i, { qty: Number(v) })}
              />
            ),
          },
          {
            title: t('quote.cost'),
            key: 'cost',
            width: 120,
            align: 'right',
            render: (_, c, i) => (
              <CommitNumber
                value={c.cost_usd === null ? null : trim(c.cost_usd)}
                min="0"
                width={104}
                disabled={readOnly}
                onCommit={(v) => void replace(i, { cost_usd: v })}
              />
            ),
          },
          {
            key: 'remove',
            width: 40,
            render: (_, _c, i) =>
              !readOnly && (
                <Button
                  size="small"
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => void onSave(parts.filter((_p, j) => j !== i))}
                />
              ),
          },
        ]}
      />
      {!readOnly && (
        <Space wrap style={{ marginTop: 8 }}>
          <div style={{ width: 360 }}>
            <ProductPicker value={productId} onChange={setProductId} deviceFilter />
          </div>
          <InputNumber
            min={1}
            precision={0}
            value={qty}
            onChange={(v) => setQty(v ?? 1)}
            addonBefore="×"
            style={{ width: 100 }}
          />
          <Button icon={<PlusOutlined />} disabled={!productId} onClick={() => void addProduct()}>
            {t('quote.addPart')}
          </Button>
          <Input
            value={name}
            placeholder={t('quote.partNamePlaceholder')}
            style={{ width: 200 }}
            onChange={(e) => setName(e.target.value)}
            onPressEnter={() => void addByHand()}
          />
          <InputNumber<string>
            stringMode
            min="0"
            value={cost}
            placeholder={t('quote.cost')}
            style={{ width: 110 }}
            onChange={(v) => setCost(v)}
          />
          <Button icon={<PlusOutlined />} disabled={!name.trim()} onClick={() => void addByHand()}>
            {t('quote.addPartByHand')}
          </Button>
        </Space>
      )}
    </div>
  )
}
