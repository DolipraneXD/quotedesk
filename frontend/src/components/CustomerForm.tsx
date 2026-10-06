import { AutoComplete, App, Button, Col, Form, Input, InputNumber, Row, Select } from 'antd'
import { useTranslation } from 'react-i18next'

import { useSaveCustomer, type Customer, type CustomerInput } from '../api/quotes'
import { errorMessage } from '../lib/i18n-helpers'

const TRADE_TERMS = ['FOB Shenzhen', 'EXW', 'CIF', 'DAP', 'DDP']

/** Create or edit a customer; ``initial`` prefills a new one (e.g. the name typed in a picker). */
export function CustomerForm({
  customer,
  initial,
  onDone,
}: {
  customer: Customer | null
  initial?: Partial<CustomerInput>
  onDone: (saved: Customer) => void
}) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const save = useSaveCustomer()
  const [form] = Form.useForm<CustomerInput>()

  const submit = async (values: CustomerInput) => {
    try {
      const saved = await save.mutateAsync({ id: customer?.id, body: values })
      message.success(t('common.saved'))
      onDone(saved)
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={customer ?? { language: 'en', ...initial }}
      onFinish={submit}
    >
      <Row gutter={12}>
        <Col span={8}>
          <Form.Item name="code" label={t('customer.code')} rules={[{ required: true }]}>
            <Input placeholder="SP002" />
          </Form.Item>
        </Col>
        <Col span={16}>
          <Form.Item name="name" label={t('customer.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="contact_name" label={t('customer.contact_name')}>
            <Input />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="email" label={t('customer.email')}>
            <Input />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="phone" label={t('customer.phone')}>
            <Input />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="trade_term" label={t('customer.trade_term')}>
            {/* free text too: "FOB Huai'nan" */}
            <AutoComplete options={TRADE_TERMS.map((v) => ({ value: v }))} allowClear />
          </Form.Item>
        </Col>
        <Col span={24}>
          <Form.Item name="address" label={t('customer.address')}>
            <Input.TextArea autoSize={{ minRows: 2 }} />
          </Form.Item>
        </Col>
        <Col span={24}>
          <Form.Item name="payment_terms" label={t('customer.payment_terms')}>
            <Input.TextArea autoSize={{ minRows: 2 }} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item
            name="default_margin_pct"
            label={t('customer.default_margin_pct')}
            extra={t('customer.marginHelp')}
          >
            <InputNumber<string> stringMode addonAfter="%" style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="language" label={t('customer.language')}>
            <Select
              options={[
                { value: 'en', label: 'English' },
                { value: 'zh', label: '中文' },
              ]}
            />
          </Form.Item>
        </Col>
        <Col span={24}>
          <Form.Item name="notes" label={t('customer.notes')}>
            <Input.TextArea autoSize={{ minRows: 2 }} />
          </Form.Item>
        </Col>
      </Row>
      <Button type="primary" htmlType="submit" loading={save.isPending}>
        {t('common.save')}
      </Button>
    </Form>
  )
}
