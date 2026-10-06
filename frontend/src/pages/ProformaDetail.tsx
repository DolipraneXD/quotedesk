import {
  ArrowLeftOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileExcelOutlined,
  StopOutlined,
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Dropdown,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Result,
  Row,
  Space,
  Spin,
  Table,
  Typography,
} from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  proformaPdfUrl,
  proformaXlsxUrl,
  useProforma,
  useProformaActions,
  type Proforma,
  type ProformaLine,
  type ProformaPatch,
  type ProformaTerm,
} from '../api/quotes'
import { CommitNumber } from '../components/quote/CommitInput'
import { DescriptionPreview } from '../components/quote/LineDetailsModal'
import { ProformaStatusTag } from '../components/quote/labels'
import { errorMessage } from '../lib/i18n-helpers'
import { formatUsd, trim } from '../lib/money'

interface HeaderValues {
  pi_no: string
  issue_date: Dayjs
  po_no: string | null
  attention: string | null
  seller_name?: string
  seller_phone?: string
  foc_pct: string | null
  freight: string | null
  terms: ProformaTerm[]
}

function toValues(pi: Proforma): HeaderValues {
  return {
    pi_no: pi.pi_no,
    issue_date: dayjs(pi.issue_date),
    po_no: pi.po_no,
    attention: pi.attention,
    seller_name: pi.seller_contact.name,
    seller_phone: pi.seller_contact.phone,
    foc_pct: pi.foc_pct === null ? null : trim(pi.foc_pct),
    freight: pi.freight === null ? null : trim(pi.freight),
    terms: pi.terms,
  }
}

export default function ProformaDetail() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const id = Number(useParams().id)
  const proforma = useProforma(id)
  const actions = useProformaActions(id)
  const [form] = Form.useForm<HeaderValues>()

  useEffect(() => {
    if (proforma.data) form.setFieldsValue(toValues(proforma.data))
  }, [proforma.data, form])

  if (proforma.isLoading) return <Spin />
  if (!proforma.data) {
    return (
      <Result
        status="404"
        title={t('errors.proforma.not_found')}
        extra={<Link to="/quotes?tab=proformas">{t('common.back')}</Link>}
      />
    )
  }
  const pi = proforma.data
  const readOnly = pi.status !== 'draft'

  const run = async (fn: () => Promise<Proforma | void>, go = false) => {
    try {
      const result = await fn()
      if (go && result) navigate(`/proformas/${result.id}`)
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  const save = async () => {
    const v = await form.validateFields()
    const body: ProformaPatch = {
      pi_no: v.pi_no,
      issue_date: v.issue_date.format('YYYY-MM-DD'),
      po_no: v.po_no || null,
      attention: v.attention || null,
      seller_contact: { name: v.seller_name ?? '', phone: v.seller_phone ?? '' },
      foc_pct: v.foc_pct || null,
      freight: v.freight || null,
      terms: v.terms,
    }
    await run(async () => {
      await actions.patch.mutateAsync(body)
      message.success(t('common.saved'))
    })
  }

  const patchLine = (line: ProformaLine, body: Partial<ProformaLine>) =>
    run(() => actions.patchLine.mutateAsync({ lineId: line.id, ...body }))

  return (
    <>
      <Link to="/quotes?tab=proformas">
        <ArrowLeftOutlined /> {t('quote.tabProformas')}
      </Link>
      <Space
        style={{ width: '100%', justifyContent: 'space-between', margin: '8px 0 16px' }}
        align="start"
        wrap
      >
        <Space direction="vertical" size={4}>
          <Typography.Title level={3} style={{ margin: 0 }}>
            {t('proforma.title')} {pi.pi_no}
          </Typography.Title>
          <Space wrap>
            <ProformaStatusTag status={pi.status} />
            <span>{pi.customer_snapshot.name}</span>
            {pi.quote_id && <Link to={`/quotes/${pi.quote_id}`}>{t('proforma.fromQuote')}</Link>}
          </Space>
        </Space>
        <Space wrap>
          <Button icon={<EyeOutlined />} href={proformaPdfUrl(pi.id)} target="_blank">
            {t('quote.preview')}
          </Button>
          <Dropdown
            menu={{
              items: [
                {
                  key: 'pdf',
                  icon: <DownloadOutlined />,
                  label: <a href={proformaPdfUrl(pi.id, true)}>PDF</a>,
                },
                {
                  key: 'xlsx',
                  icon: <FileExcelOutlined />,
                  label: <a href={proformaXlsxUrl(pi.id)}>Excel</a>,
                },
              ],
            }}
          >
            <Button icon={<DownloadOutlined />}>{t('quote.download')}</Button>
          </Dropdown>
          {pi.status === 'draft' && (
            <Popconfirm
              title={t('proforma.issueConfirm')}
              onConfirm={() => void run(() => actions.issue.mutateAsync())}
            >
              <Button type="primary">{t('proforma.issue')}</Button>
            </Popconfirm>
          )}
          {pi.status !== 'draft' && (
            <Button onClick={() => void run(() => actions.revise.mutateAsync(), true)}>
              {t('proforma.revise')}
            </Button>
          )}
          {pi.status === 'issued' && (
            <Popconfirm
              title={t('proforma.cancelConfirm')}
              onConfirm={() => void run(() => actions.cancel.mutateAsync())}
            >
              <Button danger icon={<StopOutlined />}>
                {t('proforma.cancel')}
              </Button>
            </Popconfirm>
          )}
          {pi.status === 'draft' && (
            <Popconfirm
              title={t('proforma.deleteConfirm')}
              onConfirm={() =>
                void run(async () => {
                  await actions.remove.mutateAsync()
                  navigate('/quotes?tab=proformas')
                })
              }
            >
              <Button danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      </Space>

      {readOnly && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={t(pi.status === 'issued' ? 'proforma.issuedHelp' : 'proforma.cancelledHelp')}
        />
      )}

      <Form form={form} layout="vertical" disabled={readOnly}>
        <Card size="small" title={t('proforma.header')}>
          <Row gutter={12}>
            <Col xs={12} md={6}>
              <Form.Item name="pi_no" label={t('proforma.piNo')} rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col xs={12} md={6}>
              <Form.Item name="issue_date" label={t('proforma.date')}>
                <DatePicker allowClear={false} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={12} md={6}>
              <Form.Item name="po_no" label={t('proforma.poNo')}>
                <Input />
              </Form.Item>
            </Col>
            <Col xs={12} md={6}>
              <Form.Item name="attention" label={t('proforma.attention')}>
                <Input />
              </Form.Item>
            </Col>
            <Col xs={12} md={6}>
              <Form.Item name="seller_name" label={t('proforma.sellerContact')}>
                <Input />
              </Form.Item>
            </Col>
            <Col xs={12} md={6}>
              <Form.Item name="seller_phone" label={t('proforma.sellerPhone')}>
                <Input />
              </Form.Item>
            </Col>
            <Col xs={12} md={6}>
              <Form.Item name="foc_pct" label={t('proforma.foc')} extra={t('proforma.focHelp')}>
                <InputNumber<string>
                  stringMode
                  min="0"
                  max="100"
                  addonAfter="%"
                  style={{ width: '100%' }}
                />
              </Form.Item>
            </Col>
            <Col xs={12} md={6}>
              <Form.Item name="freight" label={t('proforma.freight')}>
                <InputNumber<string> stringMode min="0" prefix="$" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Card>

        <Card size="small" title={t('proforma.lines')} style={{ marginTop: 16 }}>
          <Table<ProformaLine>
            rowKey="id"
            size="small"
            pagination={false}
            dataSource={pi.lines}
            columns={[
              { title: t('quote.modelNo'), dataIndex: 'model_no', width: 170 },
              { title: t('quote.name'), dataIndex: 'name', width: 160 },
              {
                title: t('quote.description'),
                key: 'desc',
                render: (_, line) => <DescriptionPreview lines={line.description_lines} />,
              },
              {
                title: t('quote.qty'),
                key: 'qty',
                width: 110,
                render: (_, line) => (
                  <CommitNumber
                    value={line.qty}
                    integer
                    min="1"
                    disabled={readOnly}
                    onCommit={(v) => v && void patchLine(line, { qty: Number(v) })}
                  />
                ),
              },
              {
                title: t('quote.unitPrice'),
                key: 'unit',
                width: 130,
                render: (_, line) => (
                  <CommitNumber
                    value={trim(line.unit_price)}
                    min="0"
                    width={110}
                    disabled={readOnly}
                    onCommit={(v) => v && void patchLine(line, { unit_price: v })}
                  />
                ),
              },
              {
                title: t('proforma.netAmount'),
                key: 'total',
                width: 140,
                align: 'right',
                render: (_, line) => <span className="qd-money">{formatUsd(line.total)}</span>,
              },
              {
                key: 'actions',
                width: 44,
                render: (_, line) =>
                  !readOnly &&
                  pi.lines.length > 1 && (
                    <Popconfirm
                      title={t('quote.deleteLineConfirm')}
                      onConfirm={() => void run(() => actions.deleteLine.mutateAsync(line.id))}
                    >
                      <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  ),
              },
            ]}
            summary={() => (
              <>
                {pi.freight !== null && (
                  <Table.Summary.Row>
                    <Table.Summary.Cell index={0} colSpan={5} align="right">
                      {t('proforma.freight')}
                    </Table.Summary.Cell>
                    <Table.Summary.Cell index={1} align="right">
                      {formatUsd(pi.freight)}
                    </Table.Summary.Cell>
                    <Table.Summary.Cell index={2} />
                  </Table.Summary.Row>
                )}
                <Table.Summary.Row>
                  <Table.Summary.Cell index={0} colSpan={5} align="right">
                    <Typography.Text strong>{t('proforma.total')}</Typography.Text>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={1} align="right">
                    <Typography.Text strong className="qd-money">
                      {formatUsd(pi.total)}
                    </Typography.Text>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={2} />
                </Table.Summary.Row>
              </>
            )}
          />
        </Card>

        <Card size="small" title={t('proforma.terms')} style={{ marginTop: 16 }}>
          <Form.List name="terms">
            {(fields) =>
              fields.map((field, index) => (
                <Row gutter={12} key={field.key}>
                  <Col xs={24} md={6}>
                    <Form.Item
                      name={[field.name, 'title']}
                      label={index === 0 ? t('proforma.termTitle') : undefined}
                    >
                      <Input addonBefore={index + 1} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={18}>
                    <Form.Item
                      name={[field.name, 'text']}
                      label={index === 0 ? t('proforma.termText') : undefined}
                    >
                      <Input.TextArea autoSize={{ minRows: 1, maxRows: 4 }} />
                    </Form.Item>
                  </Col>
                </Row>
              ))
            }
          </Form.List>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {t('proforma.bankHelp')} <Link to="/settings">{t('nav.settings')}</Link>
          </Typography.Paragraph>
        </Card>
        {!readOnly && (
          <Button
            type="primary"
            style={{ marginTop: 16 }}
            onClick={() => void save()}
            loading={actions.patch.isPending}
          >
            {t('common.save')}
          </Button>
        )}
      </Form>
    </>
  )
}
