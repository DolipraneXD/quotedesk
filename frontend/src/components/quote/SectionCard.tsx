import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  AppstoreAddOutlined,
  EditOutlined,
  MergeCellsOutlined,
  PlusOutlined,
  RollbackOutlined,
  SaveOutlined,
  SplitCellsOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import {
  App,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { useConfigurations, useSaveLineAsConfiguration } from '../../api/configurations'
import {
  imageUrl,
  type LinePatch,
  type ManualLineInput,
  type QuoteLine,
  type QuoteSection,
  type SectionLayout,
  useQuoteActions,
} from '../../api/quotes'
import { errorMessage } from '../../lib/i18n-helpers'
import { formatCost, formatUsd, trim } from '../../lib/money'
import ProductPicker from '../ProductPicker'
import { CommitNumber, CommitText } from './CommitInput'
import ComponentsEditor from './ComponentsEditor'
import LineDetailsModal, { DescriptionPreview } from './LineDetailsModal'
import ManualItemModal from './ManualItemModal'
import { WarningText } from './labels'

export default function SectionCard({
  quoteId,
  section,
  index,
  sections,
  readOnly,
}: {
  quoteId: number
  section: QuoteSection
  index: number
  sections: QuoteSection[]
  readOnly: boolean
}) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const actions = useQuoteActions(quoteId)
  const [details, setDetails] = useState<QuoteLine | null>(null)
  const [manual, setManual] = useState(false)
  const [productId, setProductId] = useState<number | undefined>()
  const [qty, setQty] = useState<number>(1)
  const [configId, setConfigId] = useState<number | undefined>()
  const [configQty, setConfigQty] = useState<number>(1)
  const configurations = useConfigurations()
  const saveAsConfig = useSaveLineAsConfiguration()
  const [selected, setSelected] = useState<number[]>([])
  const [combining, setCombining] = useState<'selected' | 'new' | null>(null)
  const [collapsed, setCollapsed] = useState<number[]>([])
  const combined = section.lines.filter((l) => l.kind === 'config')
  const picked = section.lines.filter((l) => selected.includes(l.id) && l.kind !== 'config')
  // the checkbox and expand columns come before ours in the summary row
  const leading = (readOnly ? 0 : 1) + (combined.length > 0 ? 1 : 0)

  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn()
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }
  const patch = (line: QuoteLine, body: LinePatch) =>
    run(() => actions.patchLine.mutateAsync({ lineId: line.id, ...body }))

  const move = (line: QuoteLine, delta: number) => {
    const ids = section.lines.map((l) => l.id)
    const from = ids.indexOf(line.id)
    const to = from + delta
    if (to < 0 || to >= ids.length) return
    ;[ids[from], ids[to]] = [ids[to], ids[from]]
    void run(() => actions.reorder.mutateAsync({ section_id: section.id, line_ids: ids }))
  }

  const addConfiguration = () => {
    if (!configId) return
    void run(async () => {
      await actions.addConfiguration.mutateAsync({
        section_id: section.id,
        configuration_id: configId,
        qty: configQty,
      })
      setConfigId(undefined)
      setConfigQty(1)
    })
  }
  const saveConfiguration = (line: QuoteLine) =>
    void run(async () => {
      await saveAsConfig.mutateAsync({ quote_id: quoteId, line_id: line.id })
      message.success(t('config.savedFromLine', { name: line.name }))
    })

  const addProduct = () => {
    if (!productId) return
    void run(async () => {
      await actions.addProduct.mutateAsync({ section_id: section.id, product_id: productId, qty })
      setProductId(undefined)
      setQty(1)
    })
  }

  return (
    <Card
      size="small"
      style={{ marginTop: 16 }}
      title={
        <Space wrap>
          <span>{t('quote.sectionN', { n: index + 1 })}</span>
          <CommitText
            value={section.title}
            disabled={readOnly}
            placeholder={
              section.layout === 'list' ? t('quote.listTitlePlaceholder') : t('quote.sectionTitle')
            }
            style={{ width: 220 }}
            onCommit={(title) =>
              void run(() => actions.patchSection.mutateAsync({ sectionId: section.id, title }))
            }
          />
          <Radio.Group
            size="small"
            optionType="button"
            value={section.layout}
            disabled={readOnly}
            onChange={(e) =>
              void run(() =>
                actions.patchSection.mutateAsync({
                  sectionId: section.id,
                  layout: e.target.value as SectionLayout,
                }),
              )
            }
            options={[
              { value: 'offer', label: t('quote.layouts.offer') },
              { value: 'list', label: t('quote.layouts.list') },
            ]}
          />
        </Space>
      }
      extra={
        !readOnly &&
        sections.length > 1 && (
          <Popconfirm
            title={t('quote.deleteSectionConfirm')}
            onConfirm={() => void run(() => actions.deleteSection.mutateAsync(section.id))}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        )
      }
    >
      <Table<QuoteLine>
        rowKey="id"
        size="small"
        pagination={false}
        dataSource={section.lines}
        scroll={{ x: 1180 }}
        locale={{ emptyText: t('quote.noLines') }}
        rowSelection={
          readOnly
            ? undefined
            : {
                selectedRowKeys: selected,
                onChange: (keys) => setSelected(keys as number[]),
                getCheckboxProps: (line) => ({ disabled: line.kind === 'config' }),
              }
        }
        expandable={
          combined.length === 0
            ? undefined
            : {
                rowExpandable: (line) => line.kind === 'config',
                expandedRowKeys: combined.map((l) => l.id).filter((id) => !collapsed.includes(id)),
                onExpand: (open, line) =>
                  setCollapsed((ids) =>
                    open ? ids.filter((id) => id !== line.id) : [...ids, line.id],
                  ),
                expandedRowRender: (line) => (
                  <ComponentsEditor
                    line={line}
                    readOnly={readOnly}
                    onSave={(components) => patch(line, { components })}
                    onDescribe={() => patch(line, { describe: true })}
                  />
                ),
              }
        }
        columns={[
          {
            title: t('quote.no'),
            key: 'no',
            width: 64,
            render: (_, line) => (
              <CommitText
                value={line.line_no}
                placeholder={line.printed_no}
                disabled={readOnly}
                style={{ width: 48 }}
                onCommit={(v) => void patch(line, { line_no: v })}
              />
            ),
          },
          {
            title: t('quote.item'),
            key: 'item',
            width: 220,
            render: (_, line) => (
              <div>
                <Space size={4} align="start">
                  <a
                    onClick={() => setDetails(line)}
                    className={line.name_emphasis ? 'qd-red' : undefined}
                  >
                    {line.name}
                  </a>
                  {line.kind === 'manual' && <Tag>{t('quote.manual')}</Tag>}
                  {line.kind === 'config' && (
                    <Tag color="purple">
                      {t('quote.combined')} · {line.components.length}
                    </Tag>
                  )}

                  {line.product_id && (
                    <Link to={`/products/${line.product_id}`} className="qd-muted">
                      #{line.product_id}
                    </Link>
                  )}
                </Space>
                {(line.model_no || line.material) && (
                  <div className="qd-muted">
                    {[line.model_no, line.material].filter(Boolean).join(' · ')}
                  </div>
                )}
                {line.configuration_id && (
                  <Link to={`/configurations/${line.configuration_id}`} className="qd-muted">
                    {t('config.saved')} #{line.configuration_id}
                  </Link>
                )}
                <div className="qd-desc-cell" onClick={() => setDetails(line)}>
                  <DescriptionPreview lines={line.description_lines.slice(0, 4)} />
                  {line.description_lines.length > 4 && (
                    <span className="qd-muted">
                      {t('quote.moreLines', { count: line.description_lines.length - 4 })}
                    </span>
                  )}
                </div>
              </div>
            ),
          },
          {
            title: t('quote.photo'),
            key: 'photo',
            width: 76,
            render: (_, line) =>
              line.image_ids.length > 0 && (
                <img className="qd-line-photo" src={imageUrl(line.image_ids[0])} alt="" />
              ),
          },
          {
            title: t('quote.qty'),
            key: 'qty',
            width: 96,
            align: 'right',
            render: (_, line) => (
              <CommitNumber
                value={line.qty}
                integer
                min="1"
                width={84}
                disabled={readOnly}
                onCommit={(v) => v && void patch(line, { qty: Number(v) })}
              />
            ),
          },
          {
            title: t('quote.cost'),
            key: 'cost',
            width: 100,
            align: 'right',
            render: (_, line) =>
              line.kind === 'manual' ? (
                <CommitNumber
                  value={line.cost_usd === null ? null : trim(line.cost_usd)}
                  min="0"
                  width={100}
                  disabled={readOnly}
                  onCommit={(v) => void patch(line, { cost_usd: v })}
                />
              ) : (
                <span className="qd-money">{formatCost(line.cost_usd) || '—'}</span>
              ),
          },
          {
            title: t('quote.margin'),
            key: 'margin',
            width: 104,
            align: 'right',
            render: (_, line) => (
              <CommitNumber
                value={line.margin_pct === null ? null : trim(line.margin_pct)}
                placeholder={
                  line.effective_margin_pct === null ? '—' : trim(line.effective_margin_pct)
                }
                addonAfter="%"
                width={96}
                disabled={readOnly || line.cost_usd === null}
                onCommit={(v) => void patch(line, { margin_pct: v })}
              />
            ),
          },
          {
            title: t('quote.unitPrice'),
            key: 'unit',
            width: 128,
            align: 'right',
            render: (_, line) => (
              <Space size={2}>
                <CommitNumber
                  value={trim(line.unit_price)}
                  min="0"
                  width={104}
                  disabled={readOnly}
                  onCommit={(v) => void patch(line, { unit_price: v })}
                />
                {line.unit_price_manual && line.cost_usd !== null && !readOnly && (
                  <Tooltip title={t('quote.resetPrice')}>
                    <Button
                      size="small"
                      type="text"
                      icon={<RollbackOutlined />}
                      onClick={() => void patch(line, { unit_price: null })}
                    />
                  </Tooltip>
                )}
              </Space>
            ),
          },
          {
            title: t('quote.total'),
            key: 'total',
            width: 120,
            align: 'right',
            render: (_, line) => <span className="qd-money">{formatUsd(line.total)}</span>,
          },
          {
            key: 'warnings',
            width: 36,
            render: (_, line) =>
              line.warnings.length > 0 && (
                <Tooltip
                  title={
                    <div>
                      {line.warnings.map((w, i) => (
                        <div key={i}>
                          <WarningText warning={w} />
                          {w.code === 'price_changed' && !readOnly && (
                            <a
                              style={{ marginLeft: 8 }}
                              onClick={() =>
                                void run(() => actions.refreshCost.mutateAsync(line.id))
                              }
                            >
                              {t('quote.useCurrentPrice')}
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  }
                >
                  <WarningOutlined style={{ color: '#d48806' }} />
                </Tooltip>
              ),
          },
          {
            key: 'actions',
            width: 172,
            fixed: 'right',
            render: (_, line, i) => (
              <Space size={0}>
                <Button
                  size="small"
                  type="text"
                  icon={<EditOutlined />}
                  onClick={() => setDetails(line)}
                />
                {line.kind === 'config' && !line.configuration_id && (
                  <Tooltip title={t('config.saveFromLine')}>
                    <Button
                      size="small"
                      type="text"
                      icon={<SaveOutlined />}
                      onClick={() => saveConfiguration(line)}
                    />
                  </Tooltip>
                )}
                {!readOnly && line.kind === 'config' && (
                  <Popconfirm
                    title={t('quote.splitConfirm')}
                    onConfirm={() => void run(() => actions.split.mutateAsync(line.id))}
                  >
                    <Tooltip title={t('quote.split')}>
                      <Button size="small" type="text" icon={<SplitCellsOutlined />} />
                    </Tooltip>
                  </Popconfirm>
                )}
                {!readOnly && (
                  <>
                    <Button
                      size="small"
                      type="text"
                      icon={<ArrowUpOutlined />}
                      disabled={i === 0}
                      onClick={() => move(line, -1)}
                    />
                    <Button
                      size="small"
                      type="text"
                      icon={<ArrowDownOutlined />}
                      disabled={i === section.lines.length - 1}
                      onClick={() => move(line, 1)}
                    />
                    <Popconfirm
                      title={t('quote.deleteLineConfirm')}
                      onConfirm={() => void run(() => actions.deleteLine.mutateAsync(line.id))}
                    >
                      <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  </>
                )}
              </Space>
            ),
          },
        ]}
        summary={() => (
          <Table.Summary.Row>
            <Table.Summary.Cell index={0} colSpan={7 + leading} align="right">
              <Typography.Text strong>{t('quote.sectionTotal')}</Typography.Text>
            </Table.Summary.Cell>
            <Table.Summary.Cell index={1} align="right">
              <Typography.Text strong className="qd-money">
                {formatUsd(section.subtotal)}
              </Typography.Text>
            </Table.Summary.Cell>
            <Table.Summary.Cell index={2} colSpan={2} />
          </Table.Summary.Row>
        )}
      />
      {!readOnly && (
        <Space wrap style={{ marginTop: 12, width: '100%' }}>
          <div style={{ width: 420 }}>
            <ProductPicker value={productId} onChange={setProductId} />
          </div>
          <InputNumber min={1} precision={0} value={qty} onChange={(v) => setQty(v ?? 1)} />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            disabled={!productId}
            loading={actions.addProduct.isPending}
            onClick={addProduct}
          >
            {t('quote.addProduct')}
          </Button>
          <Button icon={<PlusOutlined />} onClick={() => setManual(true)}>
            {t('quote.addManual')}
          </Button>
          <Button icon={<AppstoreAddOutlined />} onClick={() => setCombining('new')}>
            {t('quote.newCombined')}
          </Button>
          <Select
            showSearch
            allowClear
            value={configId}
            onChange={setConfigId}
            placeholder={t('config.insertPlaceholder')}
            optionFilterProp="label"
            style={{ width: 260 }}
            options={(configurations.data ?? []).map((c) => ({
              value: c.id,
              label: [c.name, c.model_no].filter(Boolean).join(' · '),
            }))}
          />
          <InputNumber
            min={1}
            precision={0}
            value={configQty}
            onChange={(v) => setConfigQty(v ?? 1)}
          />
          <Button
            icon={<PlusOutlined />}
            disabled={!configId}
            loading={actions.addConfiguration.isPending}
            onClick={addConfiguration}
          >
            {t('config.insert')}
          </Button>
          {picked.length >= 2 && (
            <Button
              type="primary"
              ghost
              icon={<MergeCellsOutlined />}
              onClick={() => setCombining('selected')}
            >
              {t('quote.combine', { count: picked.length })}
            </Button>
          )}
        </Space>
      )}
      {details && (
        <LineDetailsModal
          line={details}
          readOnly={readOnly}
          onSave={(body) => actions.patchLine.mutateAsync({ lineId: details.id, ...body })}
          onClose={() => setDetails(null)}
        />
      )}
      {combining && (
        <CombineModal
          mode={combining}
          defaultName={combining === 'selected' ? picked[0]?.name : ''}
          onClose={() => setCombining(null)}
          onSubmit={async (values) => {
            if (combining === 'selected') {
              await actions.combine.mutateAsync({
                line_ids: picked.map((l) => l.id),
                name: values.name,
              })
              setSelected([])
            } else {
              await actions.addCombined.mutateAsync({ section_id: section.id, ...values })
            }
            setCombining(null)
          }}
        />
      )}
      {manual && (
        <ManualItemModal
          sectionId={section.id}
          onAdd={(body: ManualLineInput) => actions.addManual.mutateAsync(body)}
          onClose={() => setManual(false)}
        />
      )}
    </Card>
  )
}

interface CombineValues {
  name: string
  qty: number
  model_no?: string | null
  material?: string | null
}

/** Name the product that several lines become, or start an empty combined product. */
function CombineModal({
  mode,
  defaultName,
  onSubmit,
  onClose,
}: {
  mode: 'selected' | 'new'
  defaultName?: string
  onSubmit: (values: CombineValues) => Promise<void>
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [form] = Form.useForm<CombineValues>()
  const [saving, setSaving] = useState(false)
  const submit = async (values: CombineValues) => {
    setSaving(true)
    try {
      await onSubmit(values)
    } catch (err) {
      message.error(errorMessage(t, err))
    } finally {
      setSaving(false)
    }
  }
  return (
    <Modal
      open
      title={mode === 'selected' ? t('quote.combineTitle') : t('quote.newCombined')}
      okText={t('common.save')}
      cancelText={t('common.cancel')}
      confirmLoading={saving}
      onOk={() => form.submit()}
      onCancel={onClose}
    >
      <Typography.Paragraph type="secondary">{t('quote.combineHelp')}</Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        initialValues={{ name: defaultName, qty: 1 }}
        onFinish={(values) => void submit(values)}
      >
        <Form.Item name="name" label={t('quote.productName')} rules={[{ required: true }]}>
          <Input autoFocus />
        </Form.Item>
        {mode === 'new' && (
          <>
            <Form.Item name="qty" label={t('quote.qty')} rules={[{ required: true }]}>
              <InputNumber min={1} precision={0} />
            </Form.Item>
            <Form.Item name="model_no" label={t('quote.modelNo')}>
              <Input />
            </Form.Item>
            <Form.Item name="material" label={t('quote.material')}>
              <Input />
            </Form.Item>
          </>
        )}
      </Form>
    </Modal>
  )
}
