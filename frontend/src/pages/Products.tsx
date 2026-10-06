import { MoreOutlined, PlusOutlined, SettingOutlined } from '@ant-design/icons'
import {
  App,
  Button,
  Checkbox,
  Dropdown,
  Input,
  Popover,
  Select,
  Space,
  Table,
  Typography,
} from 'antd'
import type { ColumnsType, TableProps } from 'antd/es/table'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import {
  useBrands,
  useCategories,
  useDeleteProduct,
  useProducts,
  useSaveProduct,
} from '../api/hooks'
import { PRODUCT_STATUSES, type Product, type ProductQuery } from '../api/types'
import CatalogStats from '../components/CatalogStats'
import MergeModal from '../components/MergeModal'
import ProductAdded from '../components/ProductSource'
import PriceEditor from '../components/PriceEditor'
import ProductForm from '../components/ProductForm'
import { FlagIcons, StatusTag } from '../components/StatusTag'
import { attributeSummary } from '../lib/attributes'
import { errorMessage, localName } from '../lib/i18n-helpers'
import { formatCost } from '../lib/money'
import { useDebounced } from '../lib/useDebounced'
import { DEVICE_TYPES } from '../lib/devices'

const OPTIONAL_COLUMNS = [
  'erp_code',
  'mpn',
  'forecast_price',
  'stock_qty',
  'stock_after_qty',
  'platform',
  'device_type',
  'notes_raw',
] as const
type OptionalColumn = (typeof OPTIONAL_COLUMNS)[number]
const COLUMNS_KEY = 'quotedesk.products.columns'

function loadColumns(): OptionalColumn[] {
  try {
    const raw = localStorage.getItem(COLUMNS_KEY)
    if (raw) return JSON.parse(raw) as OptionalColumn[]
  } catch {
    // fall back to defaults
  }
  return ['erp_code']
}

function saveColumns(cols: OptionalColumn[]) {
  try {
    localStorage.setItem(COLUMNS_KEY, JSON.stringify(cols))
  } catch {
    // per-browser convenience only
  }
}

export default function Products() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState(params.get('q') ?? '')
  const q = useDebounced(search, 250)
  const [columns, setColumns] = useState<OptionalColumn[]>(loadColumns)
  const [editing, setEditing] = useState<Product | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [merging, setMerging] = useState<Product | null>(null)

  const num = (key: string) => (params.get(key) ? Number(params.get(key)) : undefined)
  const query: ProductQuery = {
    q: q.trim() || undefined,
    category: num('category'),
    brand: num('brand'),
    status: params.get('status') ?? undefined,
    device: (params.get('device') as ProductQuery['device']) ?? undefined,
    include_general: params.get('device') ? false : undefined,
    page: num('page') ?? 1,
    page_size: num('page_size') ?? 50,
    sort: (params.get('sort') as ProductQuery['sort']) ?? 'name',
    order: (params.get('order') as ProductQuery['order']) ?? 'asc',
  }
  const products = useProducts(query)
  const categories = useCategories()
  const brands = useBrands()
  const save = useSaveProduct()
  const remove = useDeleteProduct()
  const categoryById = useMemo(
    () => new Map((categories.data ?? []).map((c) => [c.id, c])),
    [categories.data],
  )

  const setParam = (updates: Record<string, string | number | undefined>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(updates)) {
      if (v === undefined || v === '') next.delete(k)
      else next.set(k, String(v))
    }
    if (!('page' in updates)) next.delete('page')
    setParams(next, { replace: true })
  }

  const toggleStatus = async (p: Product) => {
    try {
      await save.mutateAsync({
        id: p.id,
        body: { status: p.status === 'inactive' ? 'active' : 'inactive' },
      })
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  const confirmDelete = (p: Product) =>
    modal.confirm({
      title: t('product.deleteConfirm', { name: p.name_zh }),
      okButtonProps: { danger: true },
      okText: t('common.delete'),
      onOk: async () => {
        try {
          await remove.mutateAsync(p.id)
          message.success(t('common.deleted'))
        } catch (err) {
          message.error(errorMessage(t, err))
        }
      },
    })

  const optional: Record<OptionalColumn, ColumnsType<Product>[number]> = {
    erp_code: {
      title: t('product.erp_code'),
      dataIndex: 'erp_code',
      width: 140,
      render: (v: string | null, p) =>
        v ? (
          <span>
            {v}
            {p.erp_code_alt.length > 0 && (
              <span className="qd-muted"> +{p.erp_code_alt.length}</span>
            )}
          </span>
        ) : null,
    },
    mpn: { title: t('product.mpn'), dataIndex: 'mpn', width: 160 },
    forecast_price: {
      title: t('product.forecast_price'),
      dataIndex: 'current_price_tier_forecast_usd',
      align: 'right',
      width: 120,
      render: (v: string | null) => <span className="qd-money">{formatCost(v)}</span>,
    },
    stock_qty: { title: t('product.stock_qty'), dataIndex: 'stock_qty', align: 'right', width: 90 },
    stock_after_qty: {
      title: t('product.stock_after_qty'),
      dataIndex: 'stock_after_qty',
      align: 'right',
      width: 110,
      render: (v: number | null) =>
        v !== null && v < 0 ? <Typography.Text type="danger">{v}</Typography.Text> : v,
    },
    platform: { title: t('product.platform'), dataIndex: 'platform', width: 110 },
    device_type: {
      title: t('device.label'),
      dataIndex: 'device_type',
      width: 100,
      render: (d: Product['device_type']) => (d ? t(`device.${d}`) : '—'),
    },
    notes_raw: {
      title: t('product.notes_raw'),
      dataIndex: 'notes_raw',
      ellipsis: true,
      width: 200,
    },
  }

  const sortOrder = (key: ProductQuery['sort']) =>
    query.sort === key ? (query.order === 'desc' ? 'descend' : 'ascend') : null

  const tableColumns: ColumnsType<Product> = [
    {
      title: t('product.name'),
      key: 'name',
      sorter: true,
      sortOrder: sortOrder('name'),
      render: (_, p) => {
        const summary = attributeSummary(p, categoryById.get(p.category_id), t)
        const secondary = lang === 'en' ? p.name_zh : p.name_en
        return (
          <div>
            <Link to={`/products/${p.id}`}>
              {lang === 'en' ? p.name_en || p.name_zh : p.name_zh}
            </Link>{' '}
            <FlagIcons product={p} />
            {secondary && <div className="qd-muted">{secondary}</div>}
            {summary && <div className="qd-muted">{summary}</div>}
          </div>
        )
      },
    },
    {
      title: t('product.category'),
      key: 'category',
      width: 120,
      render: (_, p) => localName(categoryById.get(p.category_id), lang),
    },
    {
      title: t('product.brand'),
      key: 'brand',
      width: 130,
      render: (_, p) =>
        p.brand ? (
          <span>
            {p.brand.canonical}
            {p.brand.name_zh && <div className="qd-muted">{p.brand.name_zh}</div>}
          </span>
        ) : null,
    },
    ...OPTIONAL_COLUMNS.filter((c) => columns.includes(c)).map((c) => ({ ...optional[c], key: c })),
    {
      title: t('product.price'),
      key: 'price',
      align: 'right',
      width: 130,
      sorter: true,
      sortOrder: sortOrder('price'),
      render: (_, p) => <PriceEditor product={p} />,
    },
    {
      title: t('product.price_date'),
      dataIndex: 'price_date',
      key: 'price_date',
      width: 110,
      sorter: true,
      sortOrder: sortOrder('price_date'),
    },
    {
      title: t('product.added'),
      key: 'created',
      width: 170,
      sorter: true,
      sortOrder: sortOrder('created'),
      render: (_, p) => <ProductAdded createdAt={p.created_at} source={p.created_import} />,
    },
    {
      title: t('product.status'),
      key: 'status',
      width: 100,
      render: (_, p) => <StatusTag status={p.status} />,
    },
    {
      key: 'actions',
      width: 48,
      render: (_, p) => (
        <Dropdown
          trigger={['click']}
          menu={{
            items: [
              {
                key: 'view',
                label: t('common.view'),
                onClick: () => navigate(`/products/${p.id}`),
              },
              {
                key: 'edit',
                label: t('common.edit'),
                onClick: () => {
                  setEditing(p)
                  setFormOpen(true)
                },
              },
              { key: 'merge', label: t('product.mergeInto'), onClick: () => setMerging(p) },
              {
                key: 'status',
                label: p.status === 'inactive' ? t('product.activate') : t('product.deactivate'),
                onClick: () => void toggleStatus(p),
              },
              { type: 'divider' },
              {
                key: 'delete',
                danger: true,
                label: t('common.delete'),
                onClick: () => confirmDelete(p),
              },
            ],
          }}
        >
          <Button type="text" icon={<MoreOutlined />} aria-label={t('common.actions')} />
        </Dropdown>
      ),
    },
  ]

  const onTableChange: TableProps<Product>['onChange'] = (pagination, _filters, sorter) => {
    const s = Array.isArray(sorter) ? sorter[0] : sorter
    const sortKey = s?.order ? (s.columnKey as string) : undefined
    setParam({
      page: pagination.current,
      page_size: pagination.pageSize,
      sort: sortKey && sortKey !== 'name' ? sortKey : undefined,
      order: s?.order === 'descend' ? 'desc' : undefined,
    })
  }

  const columnChooser = (
    <Checkbox.Group
      value={columns}
      onChange={(vals) => {
        const next = vals as OptionalColumn[]
        setColumns(next)
        saveColumns(next)
      }}
      style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
      options={OPTIONAL_COLUMNS.map((c) => ({ value: c, label: optional[c].title as string }))}
    />
  )

  return (
    <>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {t('nav.products')}
        </Typography.Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            setEditing(null)
            setFormOpen(true)
          }}
        >
          {t('product.new')}
        </Button>
      </Space>

      <CatalogStats />

      <Space wrap style={{ marginBottom: 16 }}>
        <Input.Search
          allowClear
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setParam({ q: e.target.value || undefined })
          }}
          placeholder={t('product.searchPlaceholder')}
          style={{ width: 340 }}
        />
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder={t('product.category')}
          style={{ width: 170 }}
          value={query.category}
          onChange={(v) => setParam({ category: v })}
          options={(categories.data ?? []).map((c) => ({
            value: c.id,
            label: `${localName(c, lang)} (${c.product_count})`,
          }))}
        />
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder={t('product.brand')}
          style={{ width: 170 }}
          value={query.brand}
          onChange={(v) => setParam({ brand: v })}
          options={(brands.data ?? []).map((b) => ({
            value: b.id,
            label: b.name_zh ? `${b.canonical} · ${b.name_zh}` : b.canonical,
          }))}
        />
        <Select
          allowClear
          placeholder={t('product.status')}
          style={{ width: 140 }}
          value={query.status}
          onChange={(v) => setParam({ status: v })}
          options={PRODUCT_STATUSES.map((s) => ({ value: s, label: t(`status.${s}`) }))}
        />
        <Select
          allowClear
          placeholder={t('device.label')}
          style={{ width: 140 }}
          value={query.device}
          onChange={(v) => setParam({ device: v })}
          options={[
            ...DEVICE_TYPES.map((d) => ({ value: d, label: t(`device.${d}`) })),
            { value: 'none', label: t('device.general') },
          ]}
        />
        <Popover trigger="click" content={columnChooser} title={t('product.columns')}>
          <Button icon={<SettingOutlined />}>{t('product.columns')}</Button>
        </Popover>
      </Space>

      <Table<Product>
        rowKey="id"
        size="middle"
        loading={products.isFetching}
        dataSource={products.data?.items}
        columns={tableColumns}
        onChange={onTableChange}
        scroll={{ x: 900 }}
        pagination={{
          current: query.page,
          pageSize: query.page_size,
          total: products.data?.total ?? 0,
          showSizeChanger: true,
          pageSizeOptions: [20, 50, 100, 200],
          showTotal: (total) => t('product.total', { count: total }),
        }}
        locale={{ emptyText: q ? t('common.noResults') : t('product.empty') }}
      />

      <ProductForm
        open={formOpen}
        product={editing}
        initialCategoryId={query.category}
        onClose={() => setFormOpen(false)}
      />
      {merging && <MergeModal product={merging} open onClose={() => setMerging(null)} />}
    </>
  )
}
