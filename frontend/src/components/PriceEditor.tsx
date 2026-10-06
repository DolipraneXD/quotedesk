import { EditOutlined } from '@ant-design/icons'
import { App, Button, Form, Input, InputNumber, Popover, Radio, Space } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useSetPrice } from '../api/hooks'
import type { Product } from '../api/types'
import { errorMessage } from '../lib/i18n-helpers'
import { formatCost } from '../lib/money'

interface Values {
  price_usd: string
  tier: 'standard' | 'forecast'
  note?: string
}

/** Inline price edit: each save appends a manual row to the price history. */
export default function PriceEditor({ product }: { product: Product }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm<Values>()
  const setPrice = useSetPrice()

  const submit = async (values: Values) => {
    try {
      await setPrice.mutateAsync({ id: product.id, ...values })
      message.success(t('product.priceSaved'))
      setOpen(false)
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  const content = (
    <Form
      form={form}
      layout="vertical"
      style={{ width: 240 }}
      initialValues={{ price_usd: product.current_price_usd ?? undefined, tier: 'standard' }}
      onFinish={submit}
    >
      <Form.Item name="tier" label={t('product.tier.label')}>
        <Radio.Group size="small">
          <Radio.Button value="standard">{t('product.tier.standard')}</Radio.Button>
          <Radio.Button value="forecast">{t('product.tier.forecast')}</Radio.Button>
        </Radio.Group>
      </Form.Item>
      <Form.Item name="price_usd" label={t('product.price')} rules={[{ required: true }]}>
        <InputNumber<string>
          stringMode
          min="0"
          step="0.01"
          prefix="$"
          style={{ width: '100%' }}
          autoFocus
        />
      </Form.Item>
      <Form.Item name="note" label={t('product.note')}>
        <Input />
      </Form.Item>
      <Space>
        <Button type="primary" htmlType="submit" loading={setPrice.isPending}>
          {t('common.save')}
        </Button>
        <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
      </Space>
    </Form>
  )

  return (
    <Popover
      trigger="click"
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (next) form.resetFields()
      }}
      content={content}
      title={t('product.editPrice')}
      destroyOnHidden
    >
      <Button type="link" size="small" style={{ padding: 0 }} className="qd-money">
        {product.current_price_usd ? (
          formatCost(product.current_price_usd)
        ) : (
          <span className="qd-muted">{t('product.noPrice')}</span>
        )}{' '}
        <EditOutlined style={{ fontSize: 11 }} />
      </Button>
    </Popover>
  )
}
