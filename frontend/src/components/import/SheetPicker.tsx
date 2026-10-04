import { Alert, App, Button, Image, Select, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { useCategories, useSettings } from '../../api/hooks'
import {
  isSpreadsheet,
  sourceImageUrl,
  useImportActions,
  type ImportRecord,
  type SheetSummary,
} from '../../api/imports'
import { providerKeySet } from '../../api/types'
import ColumnMappingModal from './ColumnMappingModal'
import { errorMessage, localName } from '../../lib/i18n-helpers'

function MediaPreview({ record, sheet }: { record: ImportRecord; sheet: SheetSummary }) {
  const src = sourceImageUrl(record.id, record.sheets.indexOf(sheet))
  return (
    <Space align="start" wrap size="large">
      <Image src={src} width={360} alt={sheet.name} />
      {sheet.kind === 'pdf_page' && sheet.preview.length > 0 && <Preview sheet={sheet} />}
    </Space>
  )
}

function Preview({ sheet }: { sheet: SheetSummary }) {
  const width = Math.max(0, ...sheet.preview.map((r) => r.length))
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="qd-preview">
        <tbody>
          {sheet.preview.map((cells, i) => (
            <tr key={i}>
              {Array.from({ length: width }, (_, j) => (
                <td key={j}>{cells[j] ?? ''}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Step 2 of the wizard: choose sheets and give each an optional category hint. */
export default function SheetPicker({ record }: { record: ImportRecord }) {
  const { t, i18n } = useTranslation()
  const { message } = App.useApp()
  const settings = useSettings()
  const categories = useCategories()
  const { extract } = useImportActions(record.id)
  const [selected, setSelected] = useState<string[]>(() =>
    record.sheets_selected.length
      ? record.sheets_selected
      : record.sheets.filter((s) => s.preselected).map((s) => s.name),
  )
  const [hints, setHints] = useState<Record<string, string>>(record.hints ?? {})
  const [mapping, setMapping] = useState<SheetSummary | null>(null)
  const categoryOptions = useMemo(
    () =>
      (categories.data ?? []).map((c) => ({ value: c.code, label: localName(c, i18n.language) })),
    [categories.data, i18n.language],
  )

  const start = async () => {
    try {
      await extract.mutateAsync({
        sheets: selected,
        hints: Object.fromEntries(
          Object.entries(hints).filter(([k, v]) => v && selected.includes(k)),
        ),
      })
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  const noKey = settings.data && !providerKeySet(settings.data)
  const spreadsheet = isSpreadsheet(record)

  const nameColumn: ColumnsType<SheetSummary>[number] = {
    title: spreadsheet ? t('imports.sheet') : t('imports.source'),
    dataIndex: 'name',
    render: (name: string, s) => (
      <Space size={4} wrap>
        <span>{name}</span>
        {s.hidden && <Tag>{t('imports.hidden')}</Tag>}
        {s.kind === 'sheet' && s.looks_like_price_table && (
          <Tag color="blue">{t('imports.priceTable')}</Tag>
        )}
        {s.kind !== 'sheet' && <Tag>{t(`imports.kind.${s.kind}`)}</Tag>}
        {s.scanned && <Tag color="orange">{t('imports.scanned')}</Tag>}
        {s.kind === 'image' && (
          <span className="qd-muted">
            {s.width} × {s.height}
          </span>
        )}
        {s.kind === 'pdf_page' && !s.scanned && (
          <span className="qd-muted">{t('imports.lines', { count: s.rows })}</span>
        )}
      </Space>
    ),
  }
  const sheetColumns: ColumnsType<SheetSummary> = [
    { title: t('imports.rows'), dataIndex: 'rows', align: 'right', width: 80 },
    {
      title: t('imports.headerRow'),
      dataIndex: 'header_row',
      align: 'right',
      width: 90,
      render: (v: number | null) => v ?? '—',
    },
    {
      title: t('imports.currency'),
      key: 'currency',
      width: 140,
      render: (_, s) =>
        [s.currency, s.fx_rate ? `${t('imports.rate')} ${s.fx_rate}` : null]
          .filter(Boolean)
          .join(' · ') || '—',
    },
  ]
  const mapColumn: ColumnsType<SheetSummary>[number] = {
    key: 'map',
    width: 150,
    render: (_, s) => s.rows > 0 && <a onClick={() => setMapping(s)}>{t('mapping.open')}</a>,
  }
  const hintColumn: ColumnsType<SheetSummary>[number] = {
    title: t('imports.hint'),
    key: 'hint',
    width: 200,
    render: (_, s) => (
      <Select
        allowClear
        showSearch
        optionFilterProp="label"
        size="small"
        style={{ width: '100%' }}
        placeholder={t('imports.hintAuto')}
        value={hints[s.name] || undefined}
        onChange={(v) => setHints({ ...hints, [s.name]: v })}
        options={categoryOptions}
        disabled={!selected.includes(s.name)}
      />
    ),
  }

  return (
    <>
      {noKey && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={spreadsheet ? t('imports.noKeyMapping') : t('imports.noKey')}
          action={<Link to="/settings">{t('nav.settings')}</Link>}
        />
      )}
      <Typography.Paragraph type="secondary">
        {spreadsheet ? t('imports.pickHelp') : t('imports.pickHelpMedia')}
      </Typography.Paragraph>
      <Table<SheetSummary>
        rowKey="name"
        size="small"
        pagination={false}
        dataSource={record.sheets}
        rowSelection={{
          selectedRowKeys: selected,
          onChange: (keys) => setSelected(keys as string[]),
          getCheckboxProps: (s) => ({ disabled: s.kind === 'sheet' && s.rows === 0 }),
        }}
        expandable={{
          expandedRowRender: (s) =>
            s.kind === 'sheet' ? <Preview sheet={s} /> : <MediaPreview record={record} sheet={s} />,
          rowExpandable: (s) => s.kind !== 'sheet' || s.preview.length > 0,
        }}
        columns={
          spreadsheet
            ? [nameColumn, ...sheetColumns, hintColumn, mapColumn]
            : [nameColumn, hintColumn]
        }
      />
      <Space style={{ marginTop: 16 }}>
        <Button
          type="primary"
          disabled={!selected.length || Boolean(noKey)}
          loading={extract.isPending}
          onClick={() => void start()}
        >
          {spreadsheet
            ? t('imports.extract', { count: selected.length })
            : t('imports.extractMedia', { count: selected.length })}
        </Button>
        <span className="qd-muted">
          {spreadsheet ? t('imports.extractHelp') : t('imports.extractHelpMedia')}
        </span>
      </Space>
      {mapping && (
        <ColumnMappingModal record={record} sheet={mapping} onClose={() => setMapping(null)} />
      )}
    </>
  )
}
