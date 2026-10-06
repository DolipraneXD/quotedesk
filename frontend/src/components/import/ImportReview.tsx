import { CheckOutlined } from '@ant-design/icons'
import {
  Alert,
  App,
  Badge,
  Button,
  Input,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { useCategories } from '../../api/hooks'
import {
  useImportActions,
  useImportRows,
  type ImportRecord,
  type ImportRow,
  type RowDecision,
  type RowQuery,
  type RowStatus,
} from '../../api/imports'
import { errorMessage, localName } from '../../lib/i18n-helpers'
import { formatCost } from '../../lib/money'
import { useDebounced } from '../../lib/useDebounced'
import { ROW_STATUS_COLORS } from './importLabels'
import { IssueTags, RowStatusTag } from './labels'
import RowDrawer from './RowDrawer'

const STATUSES: RowStatus[] = ['new', 'updated', 'possible_match', 'problem', 'unchanged']

function PriceCell({ row }: { row: ImportRow }) {
  const { t } = useTranslation()
  const staged = row.parsed.staged
  const price = staged?.prices?.find((p) => p.tier === 'standard') ?? staged?.prices?.[0]
  const diff = staged?.diff?.prices?.[price?.tier ?? 'standard']
  if (!price) {
    return <span className="qd-muted">{staged?.no_price_reason || t('product.noPrice')}</span>
  }
  const swing = diff?.pct && Math.abs(Number(diff.pct)) > 30
  return (
    <div className="qd-money">
      {diff && diff.old !== null && diff.old !== diff.new && (
        <span className="qd-muted">{formatCost(diff.old)} → </span>
      )}
      {formatCost(price.price_usd)}
      {diff?.pct && (
        <Tag color={swing ? 'red' : 'blue'} style={{ marginLeft: 4 }}>
          {Number(diff.pct) > 0 ? '+' : ''}
          {diff.pct}%
        </Tag>
      )}
      {price.currency_original === 'CNY' && (
        <div className="qd-muted">
          ¥{price.amount_original} @ {price.fx_rate}
        </div>
      )}
    </div>
  )
}

function decisionOptions(row: ImportRow, t: (k: string) => string) {
  const opts: { value: RowDecision; label: string }[] = []
  if (row.status === 'new') opts.push({ value: 'create', label: t('review.decision.create') })
  if (row.matched_product_id) opts.push({ value: 'update', label: t('review.decision.update') })
  opts.push({ value: 'skip', label: t('review.decision.skip') })
  return opts
}

export default function ImportReview({ record }: { record: ImportRecord }) {
  const { t, i18n } = useTranslation()
  const { message } = App.useApp()
  const categories = useCategories()
  const readOnly = record.status !== 'review'
  const [status, setStatus] = useState<RowStatus | 'all'>('all')
  const [sheet, setSheet] = useState<string>()
  const [category, setCategory] = useState<string>()
  const [search, setSearch] = useState('')
  const q = useDebounced(search, 300)
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<number[]>([])
  const [openRowId, setOpenRowId] = useState<number | null>(null)
  const [bulkCategory, setBulkCategory] = useState<string>()
  const query: RowQuery = {
    status: status === 'all' ? undefined : status,
    sheet,
    category,
    q: q || undefined,
    page,
    page_size: 100,
  }
  const rows = useImportRows(record.id, query, true)
  const actions = useImportActions(record.id)
  const counts = rows.data?.counts ?? {}
  const total = Object.values(counts).reduce((a, b) => a + (b ?? 0), 0)
  const openRow = rows.data?.items.find((r) => r.id === openRowId) ?? null
  const stats = record.stats
  const categoryName = (code?: string) =>
    localName(
      categories.data?.find((c) => c.code === code),
      i18n.language,
    ) || code

  const run = async (fn: () => Promise<unknown>, success?: string) => {
    try {
      await fn()
      if (success) message.success(success)
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  const columns: ColumnsType<ImportRow> = [
    {
      title: t('review.statusCol'),
      dataIndex: 'status',
      width: 110,
      render: (s: RowStatus) => <RowStatusTag status={s} />,
    },
    {
      title: t('review.row'),
      key: 'row',
      width: 120,
      render: (_, r) => (
        <span className="qd-muted">
          {r.sheet} · {r.row_index}
        </span>
      ),
    },
    {
      title: t('product.name'),
      key: 'name',
      width: 340,
      render: (_, r) => {
        const s = r.parsed.staged
        const name = s?.name_zh ?? r.parsed.source.name_zh
        const en = s?.name_en ?? r.parsed.source.name_en
        return (
          <div>
            <Typography.Link onClick={() => setOpenRowId(r.id)}>{name}</Typography.Link>
            {en && <div className="qd-muted">{en}</div>}
            {s?.erp_code && <div className="qd-muted">{s.erp_code}</div>}
          </div>
        )
      },
    },
    {
      title: t('product.category'),
      key: 'category',
      width: 120,
      render: (_, r) =>
        categoryName(r.parsed.staged?.category_code ?? r.parsed.source.category_code),
    },
    {
      title: t('product.brand'),
      key: 'brand',
      width: 130,
      render: (_, r) => {
        const s = r.parsed.staged
        return (
          <span>
            {s?.brand_name ?? r.parsed.source.brand}
            {s?.brand_new && (
              <Tag color="gold" style={{ marginLeft: 4 }}>
                {t('review.newBrand')}
              </Tag>
            )}
          </span>
        )
      },
    },
    {
      title: t('product.price'),
      key: 'price',
      align: 'right',
      width: 170,
      render: (_, r) => <PriceCell row={r} />,
    },
    {
      title: t('review.notes'),
      key: 'issues',
      width: 220,
      render: (_, r) => (
        <>
          {r.parsed.staged?.fields?.status && r.parsed.staged.fields.status !== 'active' && (
            <Tag color="red">{t(`status.${r.parsed.staged.fields.status}`)}</Tag>
          )}
          <IssueTags issues={r.issues} />
        </>
      ),
    },
    {
      title: t('review.decisionCol'),
      key: 'decision',
      width: 150,
      render: (_, r) =>
        r.status === 'possible_match' && !r.decision ? (
          <Button size="small" type="primary" ghost onClick={() => setOpenRowId(r.id)}>
            {t('review.decide')}
          </Button>
        ) : (
          <Select<RowDecision>
            size="small"
            style={{ width: 130 }}
            value={r.decision ?? undefined}
            disabled={readOnly}
            options={decisionOptions(r, t)}
            onChange={(decision) =>
              void run(() => actions.patchRow.mutateAsync({ rowId: r.id, decision }))
            }
          />
        ),
    },
  ]

  // deciding a possible match re-analyzes it into new/updated, so any left are undecided
  const undecided = (stats.possible_match ?? 0) > 0

  return (
    <>
      {(record.progress.errors ?? []).map((e, i) => (
        <Alert
          key={i}
          type="error"
          showIcon
          style={{ marginBottom: 8 }}
          message={
            e.rows
              ? t('imports.chunkError', { sheet: e.sheet, rows: e.rows })
              : t('imports.sourceError', { sheet: e.sheet })
          }
          description={e.message}
        />
      ))}
      {record.status === 'committed' && stats.committed && (
        <Alert
          type="success"
          showIcon
          style={{ marginBottom: 12 }}
          message={t('review.committedSummary', stats.committed)}
          description={
            stats.configurations?.length ? (
              <Space wrap>
                {t('review.unitConfigurations', { count: stats.configurations.length })}
                {stats.configurations.map((c) => (
                  <Link key={c.id} to={`/configurations/${c.id}`}>
                    {t('review.openConfiguration', { id: c.id })}
                  </Link>
                ))}
              </Space>
            ) : undefined
          }
        />
      )}
      {record.status === 'reverted' && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message={t('review.revertedNote')}
        />
      )}

      <Space wrap style={{ marginBottom: 12 }}>
        <Segmented<RowStatus | 'all'>
          value={status}
          onChange={(v) => {
            setStatus(v)
            setPage(1)
          }}
          options={[
            { value: 'all', label: `${t('review.all')} ${total}` },
            ...STATUSES.map((s) => ({
              value: s,
              label: (
                <Space size={4}>
                  <Badge
                    color={ROW_STATUS_COLORS[s] === 'default' ? '#bfbfbf' : ROW_STATUS_COLORS[s]}
                  />
                  {`${t(`review.status.${s}`)} ${counts[s] ?? 0}`}
                </Space>
              ),
            })),
          ]}
        />
      </Space>
      <Space wrap style={{ marginBottom: 12, width: '100%', justifyContent: 'space-between' }}>
        <Space wrap>
          <Select
            allowClear
            placeholder={t('imports.sheet')}
            style={{ width: 180 }}
            value={sheet}
            onChange={(v) => {
              setSheet(v)
              setPage(1)
            }}
            options={record.sheets_selected.map((s) => ({ value: s, label: s }))}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder={t('product.category')}
            style={{ width: 160 }}
            value={category}
            onChange={(v) => {
              setCategory(v)
              setPage(1)
            }}
            options={(categories.data ?? []).map((c) => ({
              value: c.code,
              label: localName(c, i18n.language),
            }))}
          />
          <Input.Search
            allowClear
            placeholder={t('review.search')}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
            style={{ width: 220 }}
          />
        </Space>
        {!readOnly && (
          <Space wrap>
            <Button
              onClick={() => void run(() => actions.bulk.mutateAsync({ action: 'skip_unchanged' }))}
            >
              {t('review.bulk.skipUnchanged')}
            </Button>
            <Button
              onClick={() => void run(() => actions.bulk.mutateAsync({ action: 'accept_updates' }))}
            >
              {t('review.bulk.acceptUpdates')}
            </Button>
          </Space>
        )}
      </Space>

      {!readOnly && selected.length > 0 && (
        <Space wrap style={{ marginBottom: 12 }}>
          <span>{t('review.selected', { count: selected.length })}</span>
          <Button
            size="small"
            onClick={() =>
              void run(() => actions.bulk.mutateAsync({ action: 'accept', row_ids: selected }))
            }
          >
            {t('review.bulk.accept')}
          </Button>
          <Button
            size="small"
            onClick={() =>
              void run(() => actions.bulk.mutateAsync({ action: 'skip', row_ids: selected }))
            }
          >
            {t('review.bulk.skip')}
          </Button>
          <Select
            size="small"
            showSearch
            optionFilterProp="label"
            placeholder={t('review.bulk.setCategory')}
            style={{ width: 170 }}
            value={bulkCategory}
            onChange={setBulkCategory}
            options={(categories.data ?? []).map((c) => ({
              value: c.code,
              label: localName(c, i18n.language),
            }))}
          />
          <Button
            size="small"
            disabled={!bulkCategory}
            onClick={() =>
              void run(() =>
                actions.bulk.mutateAsync({
                  action: 'set_category',
                  row_ids: selected,
                  category_code: bulkCategory,
                }),
              )
            }
          >
            {t('review.bulk.apply')}
          </Button>
        </Space>
      )}

      <Table<ImportRow>
        rowKey="id"
        size="small"
        loading={rows.isFetching}
        dataSource={rows.data?.items}
        columns={columns}
        scroll={{ x: 1450 }}
        rowSelection={
          readOnly
            ? undefined
            : { selectedRowKeys: selected, onChange: (keys) => setSelected(keys as number[]) }
        }
        rowClassName={(r) => (r.decision === 'skip' ? 'qd-row-skipped' : '')}
        pagination={{
          current: page,
          pageSize: 100,
          total: rows.data?.total ?? 0,
          showSizeChanger: false,
          onChange: setPage,
        }}
      />

      {!readOnly && (
        <div className="qd-review-footer">
          <span>
            {t('review.toApply', { count: stats.to_apply ?? 0 })}
            {undecided && <span className="qd-muted"> · {t('review.undecided')}</span>}
          </span>
          <Popconfirm
            title={t('review.commitConfirm', { count: stats.to_apply ?? 0 })}
            onConfirm={() => void run(() => actions.commit.mutateAsync(), t('review.committed'))}
          >
            <Button type="primary" icon={<CheckOutlined />} loading={actions.commit.isPending}>
              {t('review.commit')}
            </Button>
          </Popconfirm>
        </div>
      )}

      <RowDrawer
        importId={record.id}
        sources={record.sheets}
        row={openRow}
        readOnly={readOnly}
        onClose={() => setOpenRowId(null)}
      />
    </>
  )
}
