import { PlusOutlined } from '@ant-design/icons'
import {
  App,
  AutoComplete,
  Button,
  Col,
  Drawer,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Typography,
} from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import {
  useCustomers,
  useDeleteCustomer,
  useSaveCustomer,
  type Customer,
  type CustomerInput,
} from '../api/quotes'
import { errorMessage } from '../lib/i18n-helpers'
import { useDebounced } from '../lib/useDebounced'

const TRADE_TERMS = ['FOB Shenzhen', 'EXW', 'CIF', 'DAP', 'DDP']

function CustomerForm({ customer, onDone }: { customer: Customer | null; onDone: () => void }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const save = useSaveCustomer()
  const [form] = Form.useForm<CustomerInput>()

  const submit = async (values: CustomerInput) => {
    try {
      await save.mutateAsync({ id: customer?.id, body: values })
      message.success(t('common.saved'))
      onDone()
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={customer ?? { language: 'en' }}
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

export default function Customers() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [search, setSearch] = useState('')
  const q = useDebounced(search, 250)
  const customers = useCustomers(q)
  const remove = useDeleteCustomer()
  const [editing, setEditing] = useState<Customer | null | undefined>(undefined)

  return (
    <>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {t('nav.customers')}
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditing(null)}>
          {t('customer.new')}
        </Button>
      </Space>
      <Input.Search
        allowClear
        placeholder={t('customer.search')}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ maxWidth: 360, marginBottom: 16 }}
      />
      <Table<Customer>
        rowKey="id"
        loading={customers.isLoading}
        dataSource={customers.data}
        pagination={{ pageSize: 50, hideOnSinglePage: true }}
        locale={{ emptyText: t('customer.empty') }}
        columns={[
          { title: t('customer.code'), dataIndex: 'code', width: 110 },
          {
            title: t('customer.name'),
            dataIndex: 'name',
            render: (name: string, c) => <a onClick={() => setEditing(c)}>{name}</a>,
          },
          { title: t('customer.contact_name'), dataIndex: 'contact_name', width: 140 },
          { title: t('customer.email'), dataIndex: 'email', width: 220 },
          { title: t('customer.trade_term'), dataIndex: 'trade_term', width: 150 },
          {
            title: t('customer.default_margin_pct'),
            dataIndex: 'default_margin_pct',
            width: 110,
            align: 'right',
            render: (v: string | null) => (v === null ? '—' : `${Number(v)}%`),
          },
          {
            key: 'actions',
            width: 160,
            render: (_, c) => (
              <Space>
                <Link to={`/quotes?customer=${c.id}`}>{t('nav.quotes')}</Link>
                <Popconfirm
                  title={t('customer.deleteConfirm', { name: c.name })}
                  onConfirm={async () => {
                    try {
                      await remove.mutateAsync(c.id)
                    } catch (err) {
                      message.error(errorMessage(t, err))
                    }
                  }}
                >
                  <a className="qd-danger">{t('common.delete')}</a>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      <Drawer
        open={editing !== undefined}
        width={560}
        title={editing ? editing.name : t('customer.new')}
        onClose={() => setEditing(undefined)}
        destroyOnHidden
      >
        {editing !== undefined && (
          <CustomerForm customer={editing} onDone={() => setEditing(undefined)} />
        )}
      </Drawer>
    </>
  )
}
