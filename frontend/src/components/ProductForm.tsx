import {
  App,
  AutoComplete,
  Button,
  Checkbox,
  Col,
  DatePicker,
  Divider,
  Drawer,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Switch,
  Tooltip,
} from 'antd'
import type { Dayjs } from 'dayjs'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useBrands, useCategories, useSaveProduct } from '../api/hooks'
import {
  PRODUCT_FLAGS,
  PRODUCT_STATUSES,
  type AttributeField,
  type Brand,
  type Product,
  type ProductInput,
} from '../api/types'
import { attrLabel, errorMessage, localName } from '../lib/i18n-helpers'
import { DeviceSelect } from './DeviceSelect'

type FormValues = Omit<ProductInput, 'price_date'> & {
  flags?: string[]
  price_date?: Dayjs | null
}

interface ControlProps {
  id?: string
  value?: unknown
  onChange?: (value: unknown) => void
}

/** Form.Item injects id/value/onChange into its direct child; pass them to the control. */
function AttributeInput({
  field,
  brands,
  id,
  value,
  onChange,
}: ControlProps & { field: AttributeField; brands: Brand[] }) {
  const text = value === undefined || value === null ? undefined : String(value)
  if (field.type === 'number' || field.type === 'int') {
    return (
      <InputNumber<string>
        id={id}
        value={text}
        onChange={onChange}
        stringMode
        style={{ width: '100%' }}
        precision={field.type === 'int' ? 0 : undefined}
        addonAfter={field.unit || undefined}
      />
    )
  }
  const options =
    field.type === 'brand'
      ? brands.flatMap((b) =>
          [b.canonical, b.name_zh].filter(Boolean).map((v) => ({ value: v as string })),
        )
      : (field.options ?? []).map((o) => ({ value: o }))
  if (options.length) {
    return (
      <AutoComplete
        id={id}
        value={text}
        onChange={onChange}
        options={options}
        filterOption
        allowClear
      />
    )
  }
  return (
    <Input
      id={id}
      value={text}
      onChange={onChange}
      // capacity/frequency values are typed with their unit ("1T", "2666MHz")
      suffix={field.type === 'text' ? field.unit || undefined : undefined}
    />
  )
}

interface Props {
  open: boolean
  product?: Product | null
  initialCategoryId?: number
  onClose: () => void
  onSaved?: (p: Product) => void
}

export default function ProductForm(props: Props) {
  const { t } = useTranslation()
  return (
    <Drawer
      open={props.open}
      onClose={props.onClose}
      width={720}
      title={props.product ? t('product.edit') : t('product.new')}
      destroyOnHidden
    >
      {/* mounted per opening, so each edit starts from a fresh form store */}
      <ProductFormBody {...props} />
    </Drawer>
  )
}

function ProductFormBody({ product, initialCategoryId, onClose, onSaved }: Props) {
  const { t, i18n } = useTranslation()
  const { message } = App.useApp()
  const [form] = Form.useForm<FormValues>()
  const categories = useCategories()
  const brands = useBrands()
  const save = useSaveProduct()
  const isEdit = Boolean(product)
  const initialValues = useMemo<FormValues>(
    () =>
      product
        ? ({ ...product, flags: PRODUCT_FLAGS.filter((f) => product[f]) } as FormValues)
        : { category_id: initialCategoryId, status: 'active', flags: [] },
    [product, initialCategoryId],
  )
  const categoryId = Form.useWatch('category_id', form) ?? initialValues.category_id
  const category = categories.data?.find((c) => c.id === categoryId)

  const submit = async (values: FormValues) => {
    const { flags = [], price_date, ...rest } = values
    const body: ProductInput = { ...rest }
    for (const flag of PRODUCT_FLAGS) body[flag] = flags.includes(flag)
    if (!isEdit) body.price_date = price_date ? price_date.format('YYYY-MM-DD') : null
    // keep attribute keys the form doesn't show (extra columns from imports)
    body.attributes = { ...(product?.attributes ?? {}), ...(values.attributes ?? {}) }
    try {
      const saved = await save.mutateAsync({ id: product?.id, body })
      message.success(t('common.saved'))
      onSaved?.(saved)
      onClose()
    } catch (err) {
      if (err instanceof ApiError && err.params.existing_id) {
        message.error(
          <span>
            {errorMessage(t, err)}{' '}
            <Link to={`/products/${err.params.existing_id}`} onClick={onClose}>
              {t('common.view')}
            </Link>
          </span>,
          6,
        )
      } else {
        message.error(errorMessage(t, err))
      }
    }
  }

  const brandOptions = (brands.data ?? []).map((b) => ({
    value: b.id,
    label: b.name_zh ? `${b.canonical} · ${b.name_zh}` : b.canonical,
  }))

  return (
    <>
      <Form form={form} layout="vertical" onFinish={submit} initialValues={initialValues}>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="category_id"
              label={t('product.category')}
              rules={[{ required: true }]}
            >
              <Select
                showSearch
                optionFilterProp="label"
                options={(categories.data ?? []).map((c) => ({
                  value: c.id,
                  label: localName(c, i18n.language),
                }))}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="brand_id" label={t('product.brand')}>
              <Select showSearch allowClear optionFilterProp="label" options={brandOptions} />
            </Form.Item>
          </Col>
          <Col span={24}>
            <Form.Item
              name="name_zh"
              label={t('product.name_zh')}
              rules={[{ required: true, whitespace: true }]}
            >
              <Input />
            </Form.Item>
          </Col>
          <Col span={24}>
            <Form.Item name="name_en" label={t('product.name_en')}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="erp_code" label={t('product.erp_code')}>
              <Input placeholder="E.M.R.0000036" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="mpn" label={t('product.mpn')}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="model_no"
              label={t('product.model_no')}
              extra={t('product.modelNoHelp')}
            >
              <Input />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="material" label={t('product.material')}>
              <Input />
            </Form.Item>
          </Col>
        </Row>

        {category && category.attribute_schema.length > 0 && (
          <>
            <Divider orientation="left" plain>
              {t('product.attributes')}
            </Divider>
            <Row gutter={16}>
              {category.attribute_schema.map((field) => (
                <Col span={12} key={field.key}>
                  <Form.Item
                    name={['attributes', field.key]}
                    valuePropName={field.type === 'bool' ? 'checked' : 'value'}
                    label={
                      field.in_fingerprint ? (
                        <Tooltip title={t('product.inFingerprintHelp')}>
                          <span>
                            {attrLabel(field, i18n.language)} <span className="qd-muted">◆</span>
                          </span>
                        </Tooltip>
                      ) : (
                        attrLabel(field, i18n.language)
                      )
                    }
                  >
                    {field.type === 'bool' ? (
                      <Switch />
                    ) : (
                      <AttributeInput field={field} brands={brands.data ?? []} />
                    )}
                  </Form.Item>
                </Col>
              ))}
            </Row>
          </>
        )}

        <Divider orientation="left" plain>
          {t('product.sections.commercial')}
        </Divider>
        <Row gutter={16}>
          {!isEdit && (
            <>
              <Col span={12}>
                <Form.Item name="price_usd" label={t('product.initialPrice')}>
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
                <Form.Item name="price_date" label={t('product.price_date')}>
                  <DatePicker style={{ width: '100%' }} />
                </Form.Item>
              </Col>
            </>
          )}
          <Col span={12}>
            <Form.Item name="status" label={t('product.status')}>
              <Select
                options={PRODUCT_STATUSES.map((s) => ({ value: s, label: t(`status.${s}`) }))}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="platform" label={t('product.platform')}>
              <Input placeholder="X86 / Intel/AMD / ARM" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="device_type" label={t('device.label')} extra={t('device.productHelp')}>
              <DeviceSelect />
            </Form.Item>
          </Col>
          <Col span={24}>
            <Form.Item name="flags" label={t('product.flags')}>
              <Checkbox.Group
                options={PRODUCT_FLAGS.map((f) => ({ value: f, label: t(`flags.${f}`) }))}
              />
            </Form.Item>
          </Col>
          {(
            [
              'stock_qty',
              'demand_qty',
              'stock_after_qty',
              'max_order_qty',
              'from_stock_qty',
            ] as const
          ).map((key) => (
            <Col span={8} key={key}>
              <Form.Item name={key} label={t(`product.${key}`)}>
                <InputNumber precision={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          ))}
          <Col span={12}>
            <Form.Item name="payment_terms" label={t('product.payment_terms')}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="supply_note" label={t('product.supply_note')}>
              <Input />
            </Form.Item>
          </Col>
        </Row>

        <Divider orientation="left" plain>
          {t('product.sections.notes')}
        </Divider>
        <Form.Item name="notes_raw" label={t('product.notes_raw')}>
          <Input.TextArea autoSize={{ minRows: 1, maxRows: 4 }} />
        </Form.Item>
        <Form.Item name="description_zh" label={t('product.description_zh')}>
          <Input.TextArea autoSize={{ minRows: 2, maxRows: 6 }} />
        </Form.Item>
        <Form.Item name="description_en" label={t('product.description_en')}>
          <Input.TextArea autoSize={{ minRows: 2, maxRows: 6 }} />
        </Form.Item>
      </Form>
      <div className="qd-drawer-actions">
        <Space>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="primary" loading={save.isPending} onClick={() => form.submit()}>
            {t('common.save')}
          </Button>
        </Space>
      </div>
    </>
  )
}
