import {
  ArrowLeftOutlined,
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileDoneOutlined,
  FileExcelOutlined,
  LockOutlined,
  PlusOutlined,
  SubnodeOutlined,
} from '@ant-design/icons'
import {
  Alert,
  App,
  AutoComplete,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Dropdown,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Radio,
  Result,
  Row,
  Select,
  Space,
  Spin,
  Typography,
} from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  QUOTE_STATUSES,
  quotePdfUrl,
  quoteXlsxUrl,
  useDeleteQuote,
  useQuote,
  useQuoteActions,
  type Quote,
  type QuotePatch,
  type QuoteStatus,
} from '../api/quotes'
import { CustomerPicker } from '../components/CustomerPicker'
import ProformaCreateModal from '../components/quote/ProformaCreateModal'
import SectionCard from '../components/quote/SectionCard'
import { ProformaStatusTag, QuoteStatusTag } from '../components/quote/labels'
import { errorMessage } from '../lib/i18n-helpers'
import { formatUsd, trim } from '../lib/money'

const TRADE_TERMS = ['FOB Shenzhen', 'EXW', 'CIF', 'DAP', 'DDP']

type HeaderValues = Omit<QuotePatch, 'offer_date'> & { offer_date?: Dayjs }

function toValues(quote: Quote): HeaderValues {
  return {
    customer_id: quote.customer_id,
    offer_date: dayjs(quote.offer_date),
    validity_days: quote.validity_days,
    contact: quote.contact,
    contact_email: quote.contact_email,
    trade_term: quote.trade_term,
    payment_terms: quote.payment_terms,
    language: quote.language,
    notes_header: quote.notes_header,
    notes_footer: quote.notes_footer,
    discount_pct: quote.discount_pct === null ? null : trim(quote.discount_pct),
    discount_amount: quote.discount_amount === null ? null : trim(quote.discount_amount),
  }
}

/** Header fields save on their own, a moment after the last change (plan §5.2 autosave). */
function HeaderForm({ quote, readOnly }: { quote: Quote; readOnly: boolean }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const { patch } = useQuoteActions(quote.id)
  const [form] = Form.useForm<HeaderValues>()
  const timer = useRef<number | undefined>(undefined)
  const pending = useRef<QuotePatch>({})
  const saving = useRef(false)

  // take the server's values unless the seller is mid-edit (they would be overwritten)
  useEffect(() => {
    if (!saving.current && !Object.keys(pending.current).length) {
      form.setFieldsValue(toValues(quote))
    }
  }, [quote, form])

  const flush = async () => {
    const body = pending.current
    pending.current = {}
    if (!Object.keys(body).length) return
    saving.current = true
    try {
      await patch.mutateAsync(body)
    } catch (err) {
      message.error(errorMessage(t, err))
      form.setFieldsValue(toValues(quote))
    } finally {
      saving.current = false
    }
  }

  const onValuesChange = (changed: Partial<HeaderValues>) => {
    const body: QuotePatch = {}
    for (const [key, value] of Object.entries(changed)) {
      if (key === 'offer_date')
        body.offer_date = value ? (value as Dayjs).format('YYYY-MM-DD') : undefined
      else
        (body as Record<string, unknown>)[key] = value === '' || value === undefined ? null : value
    }
    // picking a customer refreshes contact, email and terms from it
    const immediate = 'customer_id' in body || 'language' in body
    pending.current = { ...pending.current, ...body }
    window.clearTimeout(timer.current)
    if (immediate) void flush()
    else timer.current = window.setTimeout(() => void flush(), 700)
  }

  return (
    <Form form={form} layout="vertical" disabled={readOnly} onValuesChange={onValuesChange}>
      <Row gutter={12}>
        <Col xs={24} md={8}>
          <Form.Item name="customer_id" label={t('quote.customer')}>
            <CustomerPicker />
          </Form.Item>
        </Col>
        <Col xs={12} md={4}>
          <Form.Item name="offer_date" label={t('quote.offerDate')}>
            <DatePicker allowClear={false} style={{ width: '100%' }} />
          </Form.Item>
        </Col>
        <Col xs={12} md={4}>
          <Form.Item name="validity_days" label={t('quote.validity')}>
            <InputNumber
              min={1}
              max={365}
              precision={0}
              addonAfter={t('quote.days')}
              style={{ width: '100%' }}
            />
          </Form.Item>
        </Col>
        <Col xs={12} md={4}>
          <Form.Item name="language" label={t('quote.language')}>
            <Radio.Group
              optionType="button"
              options={[
                { value: 'en', label: 'EN' },
                { value: 'zh', label: '中文' },
              ]}
            />
          </Form.Item>
        </Col>
        <Col xs={12} md={4}>
          <Form.Item name="trade_term" label={t('quote.tradeTerm')}>
            <AutoComplete options={TRADE_TERMS.map((v) => ({ value: v }))} />
          </Form.Item>
        </Col>
        <Col xs={12} md={6}>
          <Form.Item name="contact" label={t('quote.contact')}>
            <Input />
          </Form.Item>
        </Col>
        <Col xs={12} md={6}>
          <Form.Item name="contact_email" label={t('quote.email')}>
            <Input />
          </Form.Item>
        </Col>
        <Col xs={24} md={12}>
          <Form.Item name="payment_terms" label={t('quote.paymentTerms')}>
            <Input />
          </Form.Item>
        </Col>
        <Col xs={24} md={12}>
          <Form.Item name="notes_header" label={t('quote.notesHeader')}>
            <Input.TextArea autoSize={{ minRows: 1, maxRows: 4 }} />
          </Form.Item>
        </Col>
        <Col xs={24} md={12}>
          <Form.Item name="notes_footer" label={t('quote.notesFooter')}>
            <Input.TextArea autoSize={{ minRows: 1, maxRows: 4 }} />
          </Form.Item>
        </Col>
      </Row>
    </Form>
  )
}

function Totals({ quote, readOnly }: { quote: Quote; readOnly: boolean }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const { patch } = useQuoteActions(quote.id)
  const save = async (body: QuotePatch) => {
    try {
      await patch.mutateAsync(body)
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }
  return (
    <Card size="small" style={{ marginTop: 16 }}>
      <Descriptions column={1} size="small" style={{ maxWidth: 420, marginLeft: 'auto' }}>
        <Descriptions.Item label={t('quote.subtotal')}>
          <span className="qd-money">{formatUsd(quote.subtotal)}</span>
        </Descriptions.Item>
        <Descriptions.Item label={t('quote.discount')}>
          <Space>
            <InputNumber<string>
              stringMode
              size="small"
              min="0"
              max="100"
              addonAfter="%"
              disabled={readOnly}
              style={{ width: 110 }}
              defaultValue={quote.discount_pct === null ? undefined : trim(quote.discount_pct)}
              key={`pct-${quote.discount_pct}`}
              onBlur={(e) =>
                void save({
                  discount_pct: e.target.value === '' ? null : e.target.value,
                  discount_amount: null,
                })
              }
            />
            <InputNumber<string>
              stringMode
              size="small"
              min="0"
              prefix="$"
              disabled={readOnly}
              style={{ width: 130 }}
              defaultValue={
                quote.discount_amount === null ? undefined : trim(quote.discount_amount)
              }
              key={`amt-${quote.discount_amount}`}
              onBlur={(e) =>
                void save({
                  discount_amount:
                    e.target.value === '' ? null : e.target.value.replace(/[$,]/g, ''),
                  discount_pct: null,
                })
              }
            />
          </Space>
        </Descriptions.Item>
        <Descriptions.Item
          label={<Typography.Text strong>{t('quote.grandTotal')}</Typography.Text>}
        >
          <Typography.Text strong className="qd-money" style={{ fontSize: 16 }}>
            {formatUsd(quote.grand_total)}
          </Typography.Text>
        </Descriptions.Item>
      </Descriptions>
    </Card>
  )
}

export default function QuoteBuilder() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const id = Number(useParams().id)
  const quote = useQuote(id)
  const actions = useQuoteActions(id)
  const remove = useDeleteQuote()
  const [proforma, setProforma] = useState(false)

  if (quote.isLoading) return <Spin />
  if (!quote.data) {
    return (
      <Result
        status="404"
        title={t('errors.quote.not_found')}
        extra={<Link to="/quotes">{t('common.back')}</Link>}
      />
    )
  }
  const q = quote.data
  const readOnly = q.status !== 'draft'

  const run = async (fn: () => Promise<Quote | void>, go = false) => {
    try {
      const result = await fn()
      if (go && result) navigate(`/quotes/${result.id}`)
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  return (
    <>
      <Link to="/quotes">
        <ArrowLeftOutlined /> {t('nav.quotes')}
      </Link>
      <Space
        style={{ width: '100%', justifyContent: 'space-between', margin: '8px 0 16px' }}
        align="start"
        wrap
      >
        <Space direction="vertical" size={4}>
          <Typography.Title level={3} style={{ margin: 0 }}>
            {q.display_no}
          </Typography.Title>
          <Space wrap>
            <QuoteStatusTag status={q.status} />
            {q.customer_snapshot.name && <span>{q.customer_snapshot.name}</span>}
            {q.valid_until && (
              <span className="qd-muted">{t('quote.validUntil', { date: q.valid_until })}</span>
            )}
          </Space>
        </Space>
        <Space wrap>
          <Select<QuoteStatus>
            value={q.status}
            style={{ width: 140 }}
            onChange={(status) => void run(() => actions.patch.mutateAsync({ status }))}
            options={QUOTE_STATUSES.map((s) => ({ value: s, label: t(`quote.statuses.${s}`) }))}
          />
          <Button icon={<EyeOutlined />} href={quotePdfUrl(q.id)} target="_blank">
            {t('quote.customerVersion')}
          </Button>
          <Button icon={<LockOutlined />} href={quotePdfUrl(q.id, false, true)} target="_blank">
            {t('quote.internalVersion')}
          </Button>
          <Dropdown
            menu={{
              items: [
                {
                  type: 'group',
                  label: t('quote.customerVersion'),
                  children: [
                    {
                      key: 'pdf',
                      icon: <DownloadOutlined />,
                      label: <a href={quotePdfUrl(q.id, true)}>PDF</a>,
                    },
                    {
                      key: 'xlsx',
                      icon: <FileExcelOutlined />,
                      label: <a href={quoteXlsxUrl(q.id)}>Excel</a>,
                    },
                  ],
                },
                { type: 'divider' },
                {
                  type: 'group',
                  label: t('quote.internalVersion'),
                  children: [
                    {
                      key: 'internal-pdf',
                      icon: <LockOutlined />,
                      label: <a href={quotePdfUrl(q.id, true, true)}>PDF</a>,
                    },
                    {
                      key: 'internal-xlsx',
                      icon: <LockOutlined />,
                      label: <a href={quoteXlsxUrl(q.id, true)}>Excel</a>,
                    },
                  ],
                },
              ],
            }}
          >
            <Button icon={<DownloadOutlined />}>{t('quote.download')}</Button>
          </Dropdown>
          <Button
            icon={<SubnodeOutlined />}
            onClick={() => void run(() => actions.revision.mutateAsync(), true)}
          >
            {t('quote.newRevision')}
          </Button>
          <Button
            icon={<CopyOutlined />}
            onClick={() => void run(() => actions.duplicate.mutateAsync(), true)}
          >
            {t('quote.duplicate')}
          </Button>
          {q.status === 'accepted' && (
            <Button type="primary" icon={<FileDoneOutlined />} onClick={() => setProforma(true)}>
              {t('proforma.create')}
            </Button>
          )}
          <Popconfirm
            title={t('quote.deleteConfirm')}
            onConfirm={() =>
              void run(async () => {
                await remove.mutateAsync(q.id)
                navigate('/quotes')
              })
            }
          >
            <Button danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      </Space>

      {readOnly && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={t('quote.readOnly', { status: t(`quote.statuses.${q.status}`) })}
        />
      )}
      {q.revisions.length > 1 && (
        <Space wrap style={{ marginBottom: 12 }}>
          <span className="qd-muted">{t('quote.revisions')}:</span>
          {q.revisions.map((r) =>
            r.id === q.id ? (
              <strong key={r.id}>R{r.revision}</strong>
            ) : (
              <Link key={r.id} to={`/quotes/${r.id}`}>
                R{r.revision}
              </Link>
            ),
          )}
        </Space>
      )}
      {q.proformas.length > 0 && (
        <Space wrap style={{ marginBottom: 12, marginLeft: 16 }}>
          <span className="qd-muted">{t('quote.proformas')}:</span>
          {q.proformas.map((pi) => (
            <Link key={pi.id} to={`/proformas/${pi.id}`}>
              {pi.pi_no} <ProformaStatusTag status={pi.status} />
            </Link>
          ))}
        </Space>
      )}

      <Card size="small" title={t('quote.header')}>
        <HeaderForm quote={q} readOnly={readOnly} />
      </Card>

      {q.sections.map((section, index) => (
        <SectionCard
          key={section.id}
          quoteId={q.id}
          section={section}
          index={index}
          sections={q.sections}
          readOnly={readOnly}
        />
      ))}
      {!readOnly && (
        <Button
          style={{ marginTop: 12 }}
          icon={<PlusOutlined />}
          onClick={() => void run(() => actions.addSection.mutateAsync({}))}
        >
          {t('quote.addSection')}
        </Button>
      )}
      <Totals quote={q} readOnly={readOnly} />
      {proforma && <ProformaCreateModal quote={q} onClose={() => setProforma(false)} />}
    </>
  )
}
