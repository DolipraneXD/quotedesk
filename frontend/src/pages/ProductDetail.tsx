import { ArrowLeftOutlined } from '@ant-design/icons'
import {
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Result,
  Row,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'

import {
  useCategories,
  useDeleteProduct,
  usePriceHistory,
  useProduct,
  useProductAliases,
  useSaveProduct,
} from '../api/hooks'
import { PRODUCT_FLAGS, type PriceRow } from '../api/types'
import MergeModal from '../components/MergeModal'
import { ImportSource } from '../components/ProductSource'
import PriceChart from '../components/PriceChart'
import PriceEditor from '../components/PriceEditor'
import ProductForm from '../components/ProductForm'
import ProductPhotos from '../components/ProductPhotos'
import { StatusTag } from '../components/StatusTag'
import { attributeRows } from '../lib/attributes'
import { formatDateTime } from '../lib/datetime'
import { errorMessage, localName } from '../lib/i18n-helpers'
import { formatDecimal, formatCost } from '../lib/money'

export default function ProductDetail() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const id = Number(useParams().id)
  const navigate = useNavigate()
  const { message, modal } = App.useApp()
  const product = useProduct(id)
  const prices = usePriceHistory(id)
  const aliases = useProductAliases(id)
  const categories = useCategories()
  const save = useSaveProduct()
  const remove = useDeleteProduct()
  const [editOpen, setEditOpen] = useState(false)
  const [mergeOpen, setMergeOpen] = useState(false)

  if (product.isLoading) return <Spin />
  if (!product.data) {
    return (
      <Result
        status="404"
        title={t('errors.product.not_found')}
        extra={<Link to="/products">{t('common.back')}</Link>}
      />
    )
  }
  const p = product.data
  const category = categories.data?.find((c) => c.id === p.category_id)
  const flags = PRODUCT_FLAGS.filter((f) => p[f])

  const toggleStatus = async () => {
    try {
      await save.mutateAsync({
        id: p.id,
        body: { status: p.status === 'inactive' ? 'active' : 'inactive' },
      })
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  const confirmDelete = () =>
    modal.confirm({
      title: t('product.deleteConfirm', { name: p.name_zh }),
      okButtonProps: { danger: true },
      okText: t('common.delete'),
      onOk: async () => {
        try {
          await remove.mutateAsync(p.id)
          message.success(t('common.deleted'))
          navigate('/products')
        } catch (err) {
          message.error(errorMessage(t, err))
        }
      },
    })

  const show = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v))

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <Link to="/products">
          <ArrowLeftOutlined /> {t('nav.products')}
        </Link>
      </Space>
      <Space style={{ width: '100%', justifyContent: 'space-between' }} align="start" wrap>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>
            {lang === 'en' ? p.name_en || p.name_zh : p.name_zh}
          </Typography.Title>
          {p.name_en && p.name_en !== p.name_zh && (
            <div className="qd-muted">{lang === 'en' ? p.name_zh : p.name_en}</div>
          )}
          <Space style={{ marginTop: 8 }} wrap>
            <StatusTag status={p.status} />
            <Tag>{localName(category, lang)}</Tag>
            {p.is_manual && <Tag color="purple">{t('flags.is_manual')}</Tag>}
            {flags.map((f) => (
              <Tag key={f} color="gold">
                {t(`flags.${f}`)}
              </Tag>
            ))}
          </Space>
        </div>
        <Space wrap>
          <Button type="primary" onClick={() => setEditOpen(true)}>
            {t('common.edit')}
          </Button>
          <Button onClick={() => setMergeOpen(true)}>{t('product.mergeInto')}</Button>
          <Button onClick={() => void toggleStatus()}>
            {p.status === 'inactive' ? t('product.activate') : t('product.deactivate')}
          </Button>
          <Button danger onClick={confirmDelete}>
            {t('common.delete')}
          </Button>
        </Space>
      </Space>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} xl={14}>
          <Card title={t('product.details')}>
            <Descriptions column={{ xs: 1, md: 2 }} size="small">
              <Descriptions.Item label={t('product.price')}>
                <PriceEditor product={p} />
              </Descriptions.Item>
              <Descriptions.Item label={t('product.forecast_price')}>
                <span className="qd-money">
                  {show(formatCost(p.current_price_tier_forecast_usd))}
                </span>
              </Descriptions.Item>
              <Descriptions.Item label={t('product.price_date')}>
                {show(p.price_date)}
              </Descriptions.Item>
              <Descriptions.Item label={t('product.brand')}>
                {p.brand
                  ? `${p.brand.canonical}${p.brand.name_zh ? ` · ${p.brand.name_zh}` : ''}`
                  : '—'}
              </Descriptions.Item>
              <Descriptions.Item label={t('product.erp_code')}>
                {show(p.erp_code)}
                {p.erp_code_alt.length > 0 && (
                  <div className="qd-muted">{p.erp_code_alt.join(', ')}</div>
                )}
              </Descriptions.Item>
              <Descriptions.Item label={t('product.mpn')}>{show(p.mpn)}</Descriptions.Item>
              <Descriptions.Item label={t('product.platform')}>
                {show(p.platform)}
              </Descriptions.Item>
              <Descriptions.Item label={t('product.stock_qty')}>
                {show(p.stock_qty)}
              </Descriptions.Item>
              <Descriptions.Item label={t('product.demand_qty')}>
                {show(p.demand_qty)}
              </Descriptions.Item>
              <Descriptions.Item label={t('product.stock_after_qty')}>
                {p.stock_after_qty !== null && p.stock_after_qty < 0 ? (
                  <Typography.Text type="danger">{p.stock_after_qty}</Typography.Text>
                ) : (
                  show(p.stock_after_qty)
                )}
              </Descriptions.Item>
              <Descriptions.Item label={t('product.max_order_qty')}>
                {show(p.max_order_qty)}
              </Descriptions.Item>
              <Descriptions.Item label={t('product.from_stock_qty')}>
                {show(p.from_stock_qty)}
              </Descriptions.Item>
              <Descriptions.Item label={t('product.payment_terms')}>
                {show(p.payment_terms)}
              </Descriptions.Item>
              <Descriptions.Item label={t('product.supply_note')}>
                {show(p.supply_note)}
              </Descriptions.Item>
              <Descriptions.Item label={t('product.notes_raw')} span={2}>
                {show(p.notes_raw)}
              </Descriptions.Item>
              <Descriptions.Item label={t('product.added')} span={2}>
                {formatDateTime(p.created_at)} · <ImportSource source={p.created_import} />
              </Descriptions.Item>
              {p.last_import && p.last_import.id !== p.created_import_id && (
                <Descriptions.Item label={t('product.lastImport')} span={2}>
                  {formatDateTime(p.last_import.committed_at)} ·{' '}
                  <ImportSource source={p.last_import} />
                </Descriptions.Item>
              )}
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card title={t('product.attributes')}>
            {attributeRows(p, category, lang, t).length ? (
              <Descriptions column={1} size="small">
                {attributeRows(p, category, lang, t).map((row) => (
                  <Descriptions.Item
                    key={row.key}
                    label={row.inFingerprint ? <span>{row.label} ◆</span> : row.label}
                  >
                    {row.value}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
            <div className="qd-muted" style={{ marginTop: 8 }}>
              ◆ {t('product.inFingerprintHelp')}
            </div>
          </Card>
          <ProductPhotos product={p} />
        </Col>
        <Col xs={24}>
          <Card title={t('product.priceHistory')}>
            <PriceChart rows={prices.data ?? []} />
            <Table<PriceRow>
              style={{ marginTop: 16 }}
              size="small"
              rowKey="id"
              loading={prices.isLoading}
              dataSource={prices.data}
              pagination={{ pageSize: 10, hideOnSinglePage: true }}
              columns={[
                { title: t('product.price_date'), dataIndex: 'price_date', width: 110 },
                {
                  title: t('product.price'),
                  dataIndex: 'price_usd',
                  align: 'right',
                  render: (v: string) => <span className="qd-money">{formatCost(v)}</span>,
                },
                {
                  title: t('product.tier.label'),
                  dataIndex: 'tier',
                  render: (v: string) => t(`product.tier.${v}`),
                },
                {
                  title: t('product.original'),
                  key: 'original',
                  render: (_, r) =>
                    r.currency_original && r.currency_original !== 'USD'
                      ? `${formatDecimal(r.amount_original)} ${r.currency_original} @ ${formatDecimal(r.fx_rate, 4)}`
                      : '',
                },
                {
                  title: t('product.source'),
                  key: 'source',
                  render: (_, r) =>
                    r.import_id ? t('product.importNo', { id: r.import_id }) : t('product.manual'),
                },
                { title: t('product.note'), dataIndex: 'note', ellipsis: true },
                {
                  title: t('product.current'),
                  dataIndex: 'is_current',
                  render: (v: boolean) =>
                    v ? <Tag color="blue">{t('product.current')}</Tag> : null,
                },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title={t('product.aliases')}>
            <div className="qd-muted" style={{ marginBottom: 8 }}>
              {t('product.aliasesHelp')}
            </div>
            {aliases.data?.length ? (
              <ul style={{ paddingLeft: 18, margin: 0 }}>
                {aliases.data.map((a) => (
                  <li key={a.id}>
                    {a.name_zh} <span className="qd-muted">{a.fingerprint.slice(0, 10)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <span className="qd-muted">{t('product.noAliases')}</span>
            )}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card title={t('product.descriptions')}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label={t('product.description_zh')}>
                {show(p.description_zh)}
              </Descriptions.Item>
              <Descriptions.Item label={t('product.description_en')}>
                {show(p.description_en)}
              </Descriptions.Item>
              <Descriptions.Item label={t('product.fingerprint')}>
                <Typography.Text code copyable>
                  {p.fingerprint}
                </Typography.Text>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>

      <ProductForm open={editOpen} product={p} onClose={() => setEditOpen(false)} />
      <MergeModal
        product={p}
        open={mergeOpen}
        onClose={() => setMergeOpen(false)}
        onMerged={(kept) => navigate(`/products/${kept.id}`, { replace: true })}
      />
    </>
  )
}
