import { PlusOutlined, WarningOutlined } from '@ant-design/icons'
import {
  App,
  Button,
  Form,
  Input,
  Modal,
  Radio,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import {
  QUOTE_STATUSES,
  useCreateQuote,
  useProformas,
  useQuotes,
  type DocLanguage,
  type ProformaSummary,
  type QuoteSummary,
  type SectionLayout,
} from '../api/quotes'
import { CustomerPicker } from '../components/CustomerPicker'
import { ProformaStatusTag, QuoteStatusTag } from '../components/quote/labels'
import { errorMessage } from '../lib/i18n-helpers'
import { formatUsd } from '../lib/money'
import { useDebounced } from '../lib/useDebounced'

function NewQuoteModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const create = useCreateQuote()
  const [form] = Form.useForm<{
    customer_id?: number
    layout: SectionLayout
    language?: DocLanguage
  }>()

  const submit = async () => {
    const values = await form.validateFields()
    try {
      const quote = await create.mutateAsync(values)
      onClose()
      navigate(`/quotes/${quote.id}`)
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  return (
    <Modal
      open={open}
      title={t('quote.new')}
      onCancel={onClose}
      onOk={() => void submit()}
      okText={t('quote.create')}
      confirmLoading={create.isPending}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" initialValues={{ layout: 'offer' }}>
        <Form.Item name="customer_id" label={t('quote.customer')} extra={t('quote.customerHelp')}>
          <CustomerPicker onPick={(c) => form.setFieldValue('language', c.language)} />
        </Form.Item>
        <Form.Item name="layout" label={t('quote.layout')} extra={t('quote.layoutHelp')}>
          <Radio.Group
            optionType="button"
            options={[
              { value: 'offer', label: t('quote.layouts.offer') },
              { value: 'list', label: t('quote.layouts.list') },
            ]}
          />
        </Form.Item>
        <Form.Item name="language" label={t('quote.language')}>
          <Radio.Group
            optionType="button"
            options={[
              { value: 'en', label: 'English' },
              { value: 'zh', label: '中文' },
            ]}
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}

function QuoteTable() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState(params.get('q') ?? '')
  const q = useDebounced(search, 250)
  const status = params.get('status') ?? undefined
  const customer = params.get('customer') ? Number(params.get('customer')) : undefined
  const page = Number(params.get('page') ?? 1)
  const quotes = useQuotes({ q: q || undefined, status, customer, page, page_size: 50 })

  const set = (key: string, value?: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('page')
    setParams(next, { replace: true })
  }

  return (
    <>
      <Space wrap style={{ marginBottom: 16 }}>
        <Input.Search
          allowClear
          placeholder={t('quote.search')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 300 }}
        />
        <Select
          allowClear
          placeholder={t('quote.status')}
          value={status}
          onChange={(v) => set('status', v)}
          style={{ width: 160 }}
          options={QUOTE_STATUSES.map((s) => ({ value: s, label: t(`quote.statuses.${s}`) }))}
        />
        {customer && (
          <Tag closable onClose={() => set('customer')}>
            {t('quote.oneCustomer')}
          </Tag>
        )}
      </Space>
      <Table<QuoteSummary>
        rowKey="id"
        loading={quotes.isLoading}
        dataSource={quotes.data?.items}
        locale={{ emptyText: t('quote.empty') }}
        pagination={{
          current: page,
          pageSize: 50,
          total: quotes.data?.total,
          hideOnSinglePage: true,
          onChange: (p) => {
            const next = new URLSearchParams(params)
            next.set('page', String(p))
            setParams(next)
          },
        }}
        columns={[
          {
            title: t('quote.offerNo'),
            dataIndex: 'display_no',
            render: (no: string, r) => <Link to={`/quotes/${r.id}`}>{no}</Link>,
          },
          {
            title: t('quote.customer'),
            key: 'customer',
            render: (_, r) =>
              r.customer_name ? (
                <span>
                  {r.customer_name} <span className="qd-muted">{r.customer_code}</span>
                </span>
              ) : (
                '—'
              ),
          },
          {
            title: t('quote.offerDate'),
            dataIndex: 'offer_date',
            width: 120,
            render: (v: string) => dayjs(v).format('YYYY-MM-DD'),
          },
          {
            title: t('quote.status'),
            dataIndex: 'status',
            width: 110,
            render: (s: QuoteSummary['status']) => <QuoteStatusTag status={s} />,
          },
          { title: t('quote.lines'), dataIndex: 'lines', width: 80, align: 'right' },
          {
            title: t('quote.total'),
            dataIndex: 'grand_total',
            width: 150,
            align: 'right',
            render: (v: string) => <span className="qd-money">{formatUsd(v)}</span>,
          },
          {
            key: 'warnings',
            width: 48,
            render: (_, r) =>
              r.warnings > 0 && (
                <Tooltip title={t('quote.linesWithWarnings', { count: r.warnings })}>
                  <WarningOutlined style={{ color: '#d48806' }} />
                </Tooltip>
              ),
          },
        ]}
      />
    </>
  )
}

function ProformaTable() {
  const { t } = useTranslation()
  const proformas = useProformas()
  return (
    <Table<ProformaSummary>
      rowKey="id"
      loading={proformas.isLoading}
      dataSource={proformas.data}
      locale={{ emptyText: t('proforma.empty') }}
      pagination={{ pageSize: 50, hideOnSinglePage: true }}
      columns={[
        {
          title: t('proforma.piNo'),
          dataIndex: 'pi_no',
          render: (no: string, r) => <Link to={`/proformas/${r.id}`}>{no}</Link>,
        },
        {
          title: t('quote.customer'),
          key: 'customer',
          render: (_, r) => r.customer_snapshot.name ?? '—',
        },
        { title: t('proforma.date'), dataIndex: 'issue_date', width: 120 },
        {
          title: t('quote.status'),
          dataIndex: 'status',
          width: 110,
          render: (s: ProformaSummary['status']) => <ProformaStatusTag status={s} />,
        },
        {
          title: t('quote.total'),
          dataIndex: 'total',
          width: 150,
          align: 'right',
          render: (v: string) => <span className="qd-money">{formatUsd(v)}</span>,
        },
      ]}
    />
  )
}

export default function Quotes() {
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()
  const [creating, setCreating] = useState(false)
  const tab = params.get('tab') === 'proformas' ? 'proformas' : 'quotes'

  return (
    <>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 8 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {t('nav.quotes')}
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
          {t('quote.new')}
        </Button>
      </Space>
      <Tabs
        activeKey={tab}
        onChange={(key) => setParams(key === 'quotes' ? {} : { tab: key })}
        items={[
          { key: 'quotes', label: t('quote.tabQuotes'), children: <QuoteTable /> },
          { key: 'proformas', label: t('quote.tabProformas'), children: <ProformaTable /> },
        ]}
      />
      <NewQuoteModal open={creating} onClose={() => setCreating(false)} />
    </>
  )
}
