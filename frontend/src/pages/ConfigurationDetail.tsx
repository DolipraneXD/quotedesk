import {
  ArrowDownOutlined,
  ArrowLeftOutlined,
  ArrowUpOutlined,
  CloseCircleFilled,
  CopyOutlined,
  DeleteOutlined,
  PlusOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Col,
  Descriptions,
  Empty,
  Form,
  Image,
  Input,
  InputNumber,
  Popconfirm,
  Result,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  itemInput,
  useConfiguration,
  useConfigurationActions,
  useConfigurationUsage,
  type Configuration,
  type ConfigurationItem,
  type ConfigurationItemInput,
  type ConfigurationPatch,
  type ConfigurationUsage,
} from '../api/configurations'
import { imageUrl } from '../api/quotes'
import ProductPicker from '../components/ProductPicker'
import { CommitNumber, CommitText } from '../components/quote/CommitInput'
import { DescriptionPreview } from '../components/quote/LineDetailsModal'
import { QuoteStatusTag } from '../components/quote/labels'
import { errorMessage } from '../lib/i18n-helpers'
import { formatCost, formatUsd, trim } from '../lib/money'

export default function ConfigurationDetail() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const id = Number(useParams().id)
  const config = useConfiguration(id)
  const actions = useConfigurationActions(id)

  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn()
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  if (config.isLoading) return <Spin />
  if (!config.data) return <Result status="404" title={t('config.notFound')} />
  const c = config.data

  return (
    <>
      <Link to="/configurations">
        <ArrowLeftOutlined /> {t('nav.configurations')}
      </Link>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginTop: 8 }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {c.name}
        </Typography.Title>
        <Space wrap>
          <Button
            icon={<CopyOutlined />}
            onClick={() =>
              void run(async () => {
                const copy = await actions.duplicate.mutateAsync()
                navigate(`/configurations/${copy.id}`)
              })
            }
          >
            {t('config.duplicate')}
          </Button>
          <Popconfirm
            title={
              c.used_in
                ? t('config.deleteUsedConfirm', { count: c.used_in })
                : t('config.deleteConfirm')
            }
            onConfirm={() =>
              void run(async () => {
                await actions.remove.mutateAsync()
                navigate('/configurations')
              })
            }
          >
            <Button danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      </Space>

      {c.cost_changed && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 16 }}
          message={t('config.costChangedLong', {
            was: formatCost(c.saved_cost) || '—',
            now: formatCost(c.unit_cost) || '—',
          })}
          action={
            <Button size="small" onClick={() => void run(() => actions.patch.mutateAsync({}))}>
              {t('config.acceptCost')}
            </Button>
          }
        />
      )}

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <DetailsCard config={c} onSave={(body) => run(() => actions.patch.mutateAsync(body))} />
        </Col>
        <Col xs={24} lg={10}>
          <Card size="small" title={t('config.customerSees')}>
            <Descriptions size="small" column={1}>
              <Descriptions.Item label={t('config.unitCost')}>
                <span className="qd-money">{formatCost(c.unit_cost) || '—'}</span>
                {c.missing_cost > 0 && (
                  <Tag color="orange" style={{ marginLeft: 8 }}>
                    {t('config.missingCost', { count: c.missing_cost })}
                  </Tag>
                )}
              </Descriptions.Item>
            </Descriptions>
            <Typography.Text type="secondary">{t('quote.description')}</Typography.Text>
            {c.description_lines.length ? (
              <DescriptionPreview lines={c.description_lines} />
            ) : (
              <div className="qd-muted">—</div>
            )}
            <Photos config={c} run={run} />
          </Card>
        </Col>
      </Row>

      <PartsCard config={c} onSave={(items) => run(() => actions.patch.mutateAsync({ items }))} />
      <UsageCard id={c.id} />
    </>
  )
}

interface DetailsValues {
  name: string
  name_zh: string | null
  model_no: string | null
  material: string | null
  platform: string | null
  base_margin_pct: string | null
  notes: string | null
}

function DetailsCard({
  config,
  onSave,
}: {
  config: Configuration
  onSave: (body: ConfigurationPatch) => Promise<unknown>
}) {
  const { t } = useTranslation()
  const [form] = Form.useForm<DetailsValues>()
  useEffect(() => {
    form.setFieldsValue({
      name: config.name,
      name_zh: config.name_zh,
      model_no: config.model_no,
      material: config.material,
      platform: config.platform,
      base_margin_pct: config.base_margin_pct === null ? null : trim(config.base_margin_pct),
      notes: config.notes,
    })
  }, [config, form])
  const blank = (v: string | null | undefined) => (v && String(v).trim() ? v : null)
  return (
    <Card
      size="small"
      title={t('config.details')}
      extra={
        <Button type="primary" size="small" onClick={() => form.submit()}>
          {t('common.save')}
        </Button>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={(v) =>
          void onSave({
            name: v.name,
            name_zh: blank(v.name_zh),
            model_no: blank(v.model_no),
            material: blank(v.material),
            platform: blank(v.platform),
            base_margin_pct: blank(v.base_margin_pct),
            notes: blank(v.notes),
          })
        }
      >
        <Row gutter={12}>
          <Col span={12}>
            <Form.Item name="name" label={t('config.name')} rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="name_zh" label={t('config.nameZh')}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="model_no" label={t('quote.modelNo')}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="material" label={t('quote.material')}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="platform" label={t('config.platform')}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              name="base_margin_pct"
              label={t('config.margin')}
              tooltip={t('config.marginHelp')}
            >
              <InputNumber<string> stringMode addonAfter="%" style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={16}>
            <Form.Item name="notes" label={t('config.notes')}>
              <Input.TextArea autoSize={{ minRows: 1, maxRows: 4 }} />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Card>
  )
}

function Photos({
  config,
  run,
}: {
  config: Configuration
  run: (fn: () => Promise<unknown>) => Promise<void>
}) {
  const { t } = useTranslation()
  const actions = useConfigurationActions(config.id)
  return (
    <div style={{ marginTop: 12 }}>
      <Space style={{ marginBottom: 8 }}>
        <Typography.Text type="secondary">{t('quote.photos')}</Typography.Text>
        <Upload
          multiple
          accept=".png,.jpg,.jpeg,.webp"
          showUploadList={false}
          beforeUpload={(file, files) => {
            if (file === files[0]) void run(() => actions.addImages.mutateAsync(files))
            return Upload.LIST_IGNORE
          }}
        >
          <Button size="small" icon={<UploadOutlined />} loading={actions.addImages.isPending}>
            {t('product.addPhotos')}
          </Button>
        </Upload>
      </Space>
      {config.image_ids.length ? (
        <Image.PreviewGroup>
          <Space wrap>
            {config.image_ids.map((imageId) => (
              <div key={imageId} className="qd-thumb">
                <Image
                  src={imageUrl(imageId)}
                  width={120}
                  height={90}
                  style={{ objectFit: 'contain' }}
                />
                <Popconfirm
                  title={t('product.removePhoto')}
                  onConfirm={() => void run(() => actions.removeImage.mutateAsync(imageId))}
                >
                  <CloseCircleFilled className="qd-thumb-remove" />
                </Popconfirm>
              </div>
            ))}
          </Space>
        </Image.PreviewGroup>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('config.noPhotos')} />
      )}
    </div>
  )
}

/** The parts; each one is a printed description line and adds its cost. */
function PartsCard({
  config,
  onSave,
}: {
  config: Configuration
  onSave: (items: ConfigurationItemInput[]) => Promise<unknown>
}) {
  const { t } = useTranslation()
  const [productId, setProductId] = useState<number | undefined>()
  const [qty, setQty] = useState(1)
  const [name, setName] = useState('')
  const [cost, setCost] = useState<string | null>('0')
  const items = config.items.map(itemInput)

  const replace = (index: number, change: Partial<ConfigurationItemInput>) =>
    onSave(items.map((item, i) => (i === index ? { ...item, ...change } : item)))
  const move = (index: number, delta: number) => {
    const next = [...items]
    ;[next[index], next[index + delta]] = [next[index + delta], next[index]]
    void onSave(next)
  }
  const addProduct = async () => {
    if (!productId) return
    await onSave([...items, { product_id: productId, qty }])
    setProductId(undefined)
    setQty(1)
  }
  const addByHand = async () => {
    if (!name.trim()) return
    await onSave([...items, { name: name.trim(), qty, cost_usd: cost }])
    setName('')
    setCost('0')
    setQty(1)
  }

  return (
    <Card size="small" title={t('config.partsTitle')} style={{ marginTop: 16 }}>
      <Typography.Paragraph type="secondary">{t('config.partsHelp')}</Typography.Paragraph>
      <Table<ConfigurationItem>
        rowKey="id"
        size="small"
        pagination={false}
        dataSource={config.items}
        scroll={{ x: 900 }}
        locale={{ emptyText: t('quote.noParts') }}
        columns={[
          {
            title: t('config.printedText'),
            key: 'name',
            render: (_, item, i) => (
              <Space size={4}>
                <CommitText
                  value={item.name}
                  style={{ width: 320 }}
                  onCommit={(v) => v && void replace(i, { name: v })}
                />
                {item.product_id ? (
                  <Link to={`/products/${item.product_id}`} className="qd-muted">
                    #{item.product_id}
                  </Link>
                ) : (
                  <Tag>{t('quote.manual')}</Tag>
                )}
                {item.product_status && item.product_status !== 'active' && (
                  <Tag color="red">{t(`status.${item.product_status}`)}</Tag>
                )}
              </Space>
            ),
          },
          {
            title: t('config.red'),
            key: 'red',
            width: 60,
            align: 'center',
            render: (_, item, i) => (
              <Checkbox
                checked={item.emphasis}
                onChange={(e) => void replace(i, { emphasis: e.target.checked })}
              />
            ),
          },
          {
            title: t('quote.condition'),
            key: 'condition',
            width: 140,
            render: (_, item, i) => (
              <Select
                size="small"
                allowClear
                value={item.condition ?? undefined}
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
            render: (_, item, i) => (
              <CommitNumber
                value={item.qty}
                integer
                min="1"
                width={84}
                onCommit={(v) => v && void replace(i, { qty: Number(v) })}
              />
            ),
          },
          {
            title: t('quote.cost'),
            key: 'cost',
            width: 130,
            align: 'right',
            render: (_, item, i) =>
              item.product_id ? (
                <span className="qd-money" title={item.price_date ?? undefined}>
                  {formatCost(item.unit_cost) || '—'}
                </span>
              ) : (
                <CommitNumber
                  value={item.cost_usd === null ? null : trim(item.cost_usd)}
                  min="0"
                  width={110}
                  onCommit={(v) => void replace(i, { cost_usd: v })}
                />
              ),
          },
          {
            key: 'actions',
            width: 110,
            render: (_, _item, i) => (
              <Space size={0}>
                <Button
                  size="small"
                  type="text"
                  icon={<ArrowUpOutlined />}
                  disabled={i === 0}
                  onClick={() => move(i, -1)}
                />
                <Button
                  size="small"
                  type="text"
                  icon={<ArrowDownOutlined />}
                  disabled={i === items.length - 1}
                  onClick={() => move(i, 1)}
                />
                <Button
                  size="small"
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => void onSave(items.filter((_x, j) => j !== i))}
                />
              </Space>
            ),
          },
        ]}
      />
      <Space wrap style={{ marginTop: 12 }}>
        <div style={{ width: 360 }}>
          <ProductPicker value={productId} onChange={setProductId} />
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
          placeholder={t('config.specPlaceholder')}
          style={{ width: 240 }}
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
    </Card>
  )
}

function UsageCard({ id }: { id: number }) {
  const { t } = useTranslation()
  const usage = useConfigurationUsage(id)
  return (
    <Card size="small" title={t('config.whereUsed')} style={{ marginTop: 16 }}>
      <Table<ConfigurationUsage>
        rowKey="line_id"
        size="small"
        pagination={false}
        loading={usage.isLoading}
        dataSource={usage.data ?? []}
        locale={{ emptyText: t('config.notUsed') }}
        columns={[
          {
            title: t('quote.offerNo'),
            key: 'no',
            render: (_, u) => <Link to={`/quotes/${u.quote_id}`}>{u.display_no}</Link>,
          },
          {
            title: t('quote.status'),
            key: 'status',
            render: (_, u) => <QuoteStatusTag status={u.status} />,
          },
          { title: t('quote.customer'), dataIndex: 'customer_name' },
          { title: t('quote.offerDate'), dataIndex: 'offer_date' },
          { title: t('quote.qty'), dataIndex: 'qty', align: 'right' },
          {
            title: t('quote.unitPrice'),
            key: 'price',
            align: 'right',
            render: (_, u) => <span className="qd-money">{formatUsd(u.unit_price)}</span>,
          },
        ]}
      />
    </Card>
  )
}
