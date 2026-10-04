import {
  Alert,
  App,
  Col,
  Divider,
  Form,
  InputNumber,
  Modal,
  Radio,
  Row,
  Select,
  Spin,
  Typography,
} from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useCategories } from '../../api/hooks'
import {
  MAPPED_FIELDS,
  useImportActions,
  useSheetColumns,
  type ColumnMapping,
  type ImportRecord,
  type MappedField,
  type SheetColumn,
  type SheetSummary,
} from '../../api/imports'
import { attrLabel, errorMessage, localName } from '../../lib/i18n-helpers'

/** Header words that suggest a field; the last matching column wins for the price. */
const GUESS: Record<MappedField, RegExp> = {
  price: /价|price|报价|TTL|USD|RMB/i,
  erp_code: /料号|ERP|P\/N|PN\b/i,
  mpn: /原厂料号|MPN|part\s*no/i,
  brand: /品牌|brand|厂商|vendor/i,
  name_en: /english|英文/i,
  stock_qty: /^总库存$|^库存$|stock|qty on hand/i,
  demand_qty: /需求|demand/i,
  stock_after_qty: /实单后|after/i,
  notes_raw: /备注|remark|note|说明/i,
  platform: /平台|platform/i,
}

function guess(columns: SheetColumn[]): Partial<Record<MappedField, string>> {
  const result: Partial<Record<MappedField, string>> = {}
  for (const field of MAPPED_FIELDS) {
    const hits = columns.filter((c) => c.header && GUESS[field].test(c.header))
    const hit = field === 'price' ? hits[hits.length - 1] : hits[0]
    if (hit) result[field] = hit.letter
  }
  return result
}

interface Values {
  header_row: number
  category_code?: string
  name_columns: string[]
  currency: 'USD' | 'CNY'
  fx_rate?: string | null
  fields: Partial<Record<MappedField, string>>
  attributes: Record<string, string | undefined>
}

/** Import one sheet without the AI: the seller says which column holds what. */
export default function ColumnMappingModal({
  record,
  sheet,
  onClose,
}: {
  record: ImportRecord
  sheet: SheetSummary
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const { message } = App.useApp()
  const categories = useCategories()
  const { map } = useImportActions(record.id)
  const [form] = Form.useForm<Values>()
  const [headerRow, setHeaderRow] = useState<number | null>(sheet.header_row ?? 1)
  const columns = useSheetColumns(record.id, sheet.name, headerRow)
  const categoryCode = Form.useWatch('category_code', form)
  const currency = Form.useWatch('currency', form)
  const category = (categories.data ?? []).find((c) => c.code === categoryCode)

  const options = useMemo(
    () =>
      (columns.data ?? []).map((c) => ({
        value: c.letter,
        label: `${c.letter} · ${c.header || '—'}${
          c.samples.length ? `  (${c.samples.join(', ')})` : ''
        }`,
      })),
    [columns.data],
  )

  // a new header row brings new column titles: suggest a mapping from them
  useEffect(() => {
    if (!columns.data) return
    const fields = guess(columns.data)
    const nameGuess = columns.data.find((c) =>
      /名称|品名|型号|name|model|description/i.test(c.header),
    )
    form.setFieldsValue({
      fields,
      name_columns: nameGuess ? [nameGuess.letter] : [],
    })
  }, [columns.data, form])

  // the chosen category's attributes: match their labels to column titles
  useEffect(() => {
    if (!category || !columns.data) return
    const attributes: Record<string, string | undefined> = {}
    for (const field of category.attribute_schema) {
      const hit = columns.data.find(
        (c) =>
          c.header &&
          [field.label_zh, field.label_en, field.key].some(
            (label) => label && c.header.toLowerCase().includes(label.toLowerCase()),
          ),
      )
      attributes[field.key] = hit?.letter
    }
    form.setFieldsValue({ attributes })
  }, [category, columns.data, form])

  const submit = async (values: Values) => {
    const body: ColumnMapping = {
      sheet: sheet.name,
      header_row: values.header_row,
      category_code: values.category_code ?? '',
      name_columns: values.name_columns,
      fields: Object.fromEntries(
        Object.entries(values.fields ?? {}).filter(([, v]) => v),
      ) as ColumnMapping['fields'],
      attributes: Object.fromEntries(
        Object.entries(values.attributes ?? {}).filter(([, v]) => v),
      ) as Record<string, string>,
      currency: values.currency,
      fx_rate: values.currency === 'CNY' ? (values.fx_rate ?? null) : null,
    }
    try {
      await map.mutateAsync(body)
      onClose()
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  const column = (name: (string | number)[], label: string, required = false) => (
    <Form.Item name={name} label={label} rules={required ? [{ required: true }] : undefined}>
      <Select allowClear showSearch optionFilterProp="label" options={options} />
    </Form.Item>
  )

  return (
    <Modal
      open
      width={880}
      title={t('mapping.title', { sheet: sheet.name })}
      okText={t('mapping.import')}
      cancelText={t('common.cancel')}
      confirmLoading={map.isPending}
      onOk={() => form.submit()}
      onCancel={onClose}
    >
      <Typography.Paragraph type="secondary">{t('mapping.help')}</Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          header_row: sheet.header_row ?? 1,
          currency: sheet.currency === 'CNY' ? 'CNY' : 'USD',
          fx_rate: sheet.fx_rate,
          category_code: record.hints?.[sheet.name],
          name_columns: [],
          fields: {},
          attributes: {},
        }}
        onFinish={(v) => void submit(v)}
      >
        <Row gutter={16}>
          <Col span={6}>
            <Form.Item
              name="header_row"
              label={t('mapping.headerRow')}
              rules={[{ required: true }]}
            >
              <InputNumber min={1} precision={0} onChange={(v) => setHeaderRow(v)} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              name="category_code"
              label={t('mapping.category')}
              rules={[{ required: true }]}
            >
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
          <Col span={5}>
            <Form.Item name="currency" label={t('mapping.currency')}>
              <Radio.Group
                optionType="button"
                options={[
                  { value: 'USD', label: 'USD' },
                  { value: 'CNY', label: 'CNY' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col span={5}>
            {currency === 'CNY' && (
              <Form.Item name="fx_rate" label={t('mapping.fxRate')} tooltip={t('mapping.fxHelp')}>
                <InputNumber<string> stringMode min="0" style={{ width: '100%' }} />
              </Form.Item>
            )}
          </Col>
        </Row>
        {columns.isLoading ? (
          <Spin />
        ) : columns.data?.length === 0 ? (
          <Alert type="warning" showIcon message={t('mapping.noColumns')} />
        ) : (
          <>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item
                  name="name_columns"
                  label={t('mapping.name')}
                  tooltip={t('mapping.nameHelp')}
                  rules={[{ required: true }]}
                >
                  <Select mode="multiple" optionFilterProp="label" options={options} />
                </Form.Item>
              </Col>
              <Col span={12}>{column(['fields', 'price'], t('mapping.fields.price'), true)}</Col>
              {MAPPED_FIELDS.filter((f) => f !== 'price').map((f) => (
                <Col span={8} key={f}>
                  {column(['fields', f], t(`mapping.fields.${f}`))}
                </Col>
              ))}
            </Row>
            {category && category.attribute_schema.length > 0 && (
              <>
                <Divider orientation="left" plain>
                  {t('mapping.attributes', { category: localName(category, i18n.language) })}
                </Divider>
                <Row gutter={16}>
                  {category.attribute_schema.map((field) => (
                    <Col span={8} key={field.key}>
                      {column(
                        ['attributes', field.key],
                        attrLabel(field, i18n.language) + (field.in_fingerprint ? ' *' : ''),
                      )}
                    </Col>
                  ))}
                </Row>
                <Typography.Text type="secondary">{t('mapping.attributesHelp')}</Typography.Text>
              </>
            )}
          </>
        )}
      </Form>
    </Modal>
  )
}
