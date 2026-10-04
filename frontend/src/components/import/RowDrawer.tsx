import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import {
  Alert,
  App,
  AutoComplete,
  Button,
  Col,
  Descriptions,
  Divider,
  Drawer,
  Form,
  Image,
  Input,
  InputNumber,
  Radio,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { useBrands, useCategories } from '../../api/hooks'
import {
  sourceImageUrl,
  useImportActions,
  type ImportRow,
  type SheetSummary,
} from '../../api/imports'
import { PRODUCT_STATUSES } from '../../api/types'
import { attrLabel, errorMessage, localName } from '../../lib/i18n-helpers'
import { formatCost } from '../../lib/money'
import { IssueTags, RowStatusTag } from './labels'

interface FormValues {
  category_code?: string
  name_zh?: string
  name_en?: string
  brand?: string
  mpn?: string
  erp_codes?: string[]
  price_usd?: string
  status?: string
  notes_raw?: string
  attributes?: { key: string; value: string }[]
}

/** Review one extracted row: compare with the source cells, fix fields, decide the match. */
export default function RowDrawer({
  importId,
  sources,
  row,
  readOnly,
  onClose,
}: {
  importId: number
  sources: SheetSummary[]
  row: ImportRow | null
  readOnly: boolean
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const { message } = App.useApp()
  const categories = useCategories()
  const brands = useBrands()
  const { patchRow } = useImportActions(importId)
  const [form] = Form.useForm<FormValues>()
  const staged = row?.parsed.staged
  const source = row?.parsed.source
  const sourceIndex = sources.findIndex((s) => s.name === row?.sheet)
  const sourceInfo = sourceIndex >= 0 ? sources[sourceIndex] : undefined
  const category = categories.data?.find(
    (c) => c.code === (staged?.category_code ?? source?.category_code),
  )

  const initial = useMemo<FormValues>(() => {
    if (!row) return {}
    const s = row.parsed.staged ?? {}
    const src = row.parsed.source
    const attrs = s.attributes ?? Object.fromEntries(src.attributes.map((a) => [a.key, a.value]))
    return {
      category_code: s.category_code ?? src.category_code,
      name_zh: s.name_zh ?? src.name_zh,
      name_en: s.name_en ?? src.name_en ?? '',
      brand: s.brand_name ?? src.brand ?? '',
      mpn: s.mpn ?? src.mpn ?? '',
      erp_codes: [s.erp_code, ...(s.erp_code_alt ?? [])].filter(Boolean) as string[],
      price_usd: (row.user_edits.price_usd as string | undefined) ?? undefined,
      status: (row.user_edits.status as string | undefined) ?? s.fields?.status,
      notes_raw: src.notes_raw ?? '',
      attributes: Object.entries(attrs).map(([key, value]) => ({ key, value: String(value) })),
    }
  }, [row])

  if (!row) return null

  const patch = async (body: {
    edits?: Record<string, unknown>
    decision?: 'create' | 'update' | 'skip'
  }) => {
    try {
      await patchRow.mutateAsync({ rowId: row.id, ...body })
      message.success(t('common.saved'))
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  const save = async (values: FormValues) => {
    const edits: Record<string, unknown> = {}
    const changed = (key: keyof FormValues) =>
      JSON.stringify(values[key] ?? '') !== JSON.stringify(initial[key] ?? '')
    for (const key of [
      'category_code',
      'name_zh',
      'name_en',
      'brand',
      'mpn',
      'status',
      'notes_raw',
    ] as const) {
      if (changed(key)) edits[key] = values[key] ?? ''
    }
    if (changed('erp_codes')) edits.erp_codes = values.erp_codes ?? []
    if (values.price_usd) edits.price_usd = values.price_usd
    if (changed('attributes')) {
      const next = Object.fromEntries(
        (values.attributes ?? []).filter((a) => a?.key).map((a) => [a.key, a.value ?? '']),
      )
      // keys removed in the form are sent empty so the extracted value is dropped too
      for (const a of initial.attributes ?? []) if (!(a.key in next)) next[a.key] = ''
      edits.attributes = next
    }
    if (!Object.keys(edits).length) return
    await patch({ edits })
  }

  const resetEdits = () =>
    patch({
      edits: Object.fromEntries(
        Object.keys(row.user_edits)
          .filter((k) => k !== 'decision')
          .map((k) => [k, null]),
      ),
    })

  const choice = row.user_edits.force_new
    ? 'new'
    : row.match_type === 'manual'
      ? String(row.matched_product_id)
      : undefined

  return (
    <Drawer
      open
      width={760}
      onClose={onClose}
      destroyOnHidden
      title={
        <Space>
          <RowStatusTag status={row.status} />
          <span>{`${row.sheet} · ${t('review.row')} ${row.row_index}`}</span>
        </Space>
      }
    >
      <IssueTags issues={row.issues} />

      {(row.candidates.length > 0 ||
        row.match_type === 'manual' ||
        Boolean(row.user_edits.force_new)) && (
        <>
          <Divider orientation="left" plain>
            {t('review.possibleMatch')}
          </Divider>
          <Alert
            type="warning"
            showIcon
            message={t('review.possibleMatchHelp')}
            style={{ marginBottom: 12 }}
          />
          <Radio.Group
            value={choice}
            disabled={readOnly || patchRow.isPending}
            onChange={(e) =>
              patch({
                edits:
                  e.target.value === 'new'
                    ? { force_new: true }
                    : { match_product_id: Number(e.target.value) },
              })
            }
          >
            <Space direction="vertical">
              {row.candidates.map((c) => (
                <Radio key={c.product_id} value={String(c.product_id)}>
                  {t('review.useExisting')}:{' '}
                  <Link to={`/products/${c.product_id}`}>{c.name_zh}</Link>{' '}
                  <span className="qd-muted">{Math.round(c.score * 100)}%</span>
                </Radio>
              ))}
              <Radio value="new">{t('review.createNew')}</Radio>
            </Space>
          </Radio.Group>
        </>
      )}

      {row.matched_product_id && row.match_type !== 'manual' && (
        <div style={{ marginTop: 12 }}>
          {t('review.matchedBy', { type: t(`review.matchType.${row.match_type}`) })}{' '}
          <Link to={`/products/${row.matched_product_id}`}>#{row.matched_product_id}</Link>
        </div>
      )}

      {staged?.diff && (
        <Descriptions size="small" column={1} style={{ marginTop: 12 }}>
          {Object.entries(staged.diff.prices).map(([tier, d]) => (
            <Descriptions.Item key={tier} label={t(`product.tier.${tier}`)}>
              <span className="qd-money">
                {formatCost(d.old) || '—'} → {formatCost(d.new)}
              </span>{' '}
              {d.pct && <Tag color={Math.abs(Number(d.pct)) > 30 ? 'red' : 'blue'}>{d.pct}%</Tag>}
            </Descriptions.Item>
          ))}
          {staged.diff.fields.length > 0 && (
            <Descriptions.Item label={t('review.changedFields')}>
              {staged.diff.fields.map((f) => (
                <Tag key={f}>{t(`review.field.${f}`, { defaultValue: f })}</Tag>
              ))}
            </Descriptions.Item>
          )}
        </Descriptions>
      )}

      <Divider orientation="left" plain>
        {sourceInfo && sourceInfo.kind !== 'sheet' ? t('review.sourceImage') : t('review.source')}
      </Divider>
      {sourceInfo && sourceInfo.kind !== 'sheet' && (
        <div style={{ marginBottom: 12 }}>
          {(sourceInfo.kind === 'image' || sourceInfo.scanned) && (
            <div style={{ marginBottom: 6 }}>{t('review.imagePosition', { n: row.row_index })}</div>
          )}
          <Image
            src={sourceImageUrl(importId, sourceIndex)}
            alt={sourceInfo.name}
            style={{ maxHeight: 420, objectFit: 'contain' }}
          />
          <div className="qd-muted">{t('review.zoomHint')}</div>
        </div>
      )}
      {Object.keys(row.raw).length > 0 && (
        <Descriptions size="small" column={2} bordered>
          {Object.entries(row.raw).map(([ref, value]) => (
            <Descriptions.Item key={ref} label={ref}>
              {value}
            </Descriptions.Item>
          ))}
        </Descriptions>
      )}

      <Divider orientation="left" plain>
        {t('review.extracted')}
      </Divider>
      <Form
        key={row.id + JSON.stringify(row.user_edits)}
        form={form}
        layout="vertical"
        initialValues={initial}
        onFinish={save}
        disabled={readOnly}
      >
        <Row gutter={12}>
          <Col span={12}>
            <Form.Item name="category_code" label={t('product.category')}>
              <Select
                showSearch
                optionFilterProp="label"
                options={(categories.data ?? []).map((c) => ({
                  value: c.code,
                  label: localName(c, i18n.language),
                }))}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="brand"
              label={
                <span>
                  {t('product.brand')}{' '}
                  {staged?.brand_new && <Tag color="gold">{t('review.newBrand')}</Tag>}
                </span>
              }
            >
              <AutoComplete
                allowClear
                filterOption
                options={(brands.data ?? []).map((b) => ({ value: b.canonical }))}
              />
            </Form.Item>
          </Col>
          <Col span={24}>
            <Form.Item name="name_zh" label={t('product.name_zh')} rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={24}>
            <Form.Item name="name_en" label={t('product.name_en')}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="erp_codes" label={t('product.erp_code')}>
              <Select mode="tags" tokenSeparators={['/', ',', ' ']} open={false} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="mpn" label={t('product.mpn')}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="price_usd"
              label={t('review.priceOverride')}
              extra={
                staged?.prices?.length
                  ? staged.prices
                      .map(
                        (p) =>
                          `${t(`product.tier.${p.tier}`)} ${formatCost(p.price_usd)}` +
                          (p.currency_original === 'CNY'
                            ? ` (¥${p.amount_original} @ ${p.fx_rate})`
                            : ''),
                      )
                      .join(' · ')
                  : `${t('product.noPrice')}${staged?.no_price_reason ? `: ${staged.no_price_reason}` : ''}`
              }
            >
              <InputNumber<string>
                stringMode
                min="0"
                step="0.01"
                prefix="$"
                style={{ width: '100%' }}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="status" label={t('product.status')}>
              <Select
                options={PRODUCT_STATUSES.map((s) => ({ value: s, label: t(`status.${s}`) }))}
              />
            </Form.Item>
          </Col>
          <Col span={24}>
            <Form.Item name="notes_raw" label={t('product.notes_raw')}>
              <Input.TextArea autoSize={{ minRows: 1, maxRows: 4 }} />
            </Form.Item>
          </Col>
        </Row>
        <Typography.Text strong>{t('product.attributes')}</Typography.Text>
        <Form.List name="attributes">
          {(fields, { add, remove }) => (
            <div style={{ marginTop: 8 }}>
              {fields.map((field) => {
                const key = form.getFieldValue(['attributes', field.name, 'key']) as
                  string | undefined
                const schemaField = category?.attribute_schema.find((f) => f.key === key)
                return (
                  <Row gutter={8} key={field.key} align="middle">
                    <Col span={9}>
                      <Form.Item name={[field.name, 'key']} style={{ marginBottom: 8 }}>
                        <AutoComplete
                          options={(category?.attribute_schema ?? []).map((f) => ({
                            value: f.key,
                            label: `${f.key} · ${attrLabel(f, i18n.language)}`,
                          }))}
                        />
                      </Form.Item>
                    </Col>
                    <Col span={13}>
                      <Form.Item name={[field.name, 'value']} style={{ marginBottom: 8 }}>
                        <Input
                          suffix={
                            schemaField?.in_fingerprint ? (
                              <span className="qd-muted">◆</span>
                            ) : undefined
                          }
                        />
                      </Form.Item>
                    </Col>
                    <Col span={2}>
                      <Button
                        type="text"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => remove(field.name)}
                        aria-label={t('common.remove')}
                      />
                    </Col>
                  </Row>
                )
              })}
              <Button
                type="dashed"
                size="small"
                icon={<PlusOutlined />}
                onClick={() => add({ key: '', value: '' })}
              >
                {t('category.addAttr')}
              </Button>
            </div>
          )}
        </Form.List>
        {!readOnly && (
          <div className="qd-drawer-actions">
            <Space>
              {Object.keys(row.user_edits).some((k) => k !== 'decision') && (
                <Button onClick={() => void resetEdits()}>{t('review.resetEdits')}</Button>
              )}
              <Button type="primary" htmlType="submit" loading={patchRow.isPending}>
                {t('review.saveEdits')}
              </Button>
            </Space>
          </div>
        )}
      </Form>
    </Drawer>
  )
}
