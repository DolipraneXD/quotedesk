import { DeleteOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons'
import {
  App,
  Button,
  Card,
  Col,
  Drawer,
  Form,
  Image,
  Input,
  InputNumber,
  Popconfirm,
  Radio,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
} from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  useBrandMutations,
  useBrands,
  useCategories,
  useSaveCategory,
  useSaveSettings,
  useSettings,
} from '../api/hooks'
import { useTestLlm } from '../api/imports'
import { imageUrl, useCompanyImage } from '../api/quotes'
import type {
  ApiKeysIn,
  LlmProvider,
  AttributeField,
  AttributeType,
  Brand,
  Category,
  Settings as SettingsT,
} from '../api/types'
import BackupsTab from '../components/settings/BackupsTab'
import NoteRulesTab from '../components/settings/NoteRulesTab'
import { errorMessage, localName } from '../lib/i18n-helpers'

const ATTRIBUTE_TYPES: AttributeType[] = [
  'text',
  'number',
  'int',
  'capacity',
  'frequency',
  'form_factor',
  'interface',
  'brand',
  'bool',
]

type FormValues = SettingsT & ApiKeysIn

const PROVIDERS: {
  provider: LlmProvider
  keyField: keyof ApiKeysIn
  keySetField:
    'anthropic_api_key_set' | 'gemini_api_key_set' | 'groq_api_key_set' | 'inception_api_key_set'
  modelField: 'llm_model' | 'gemini_model' | 'groq_model' | 'inception_model'
  placeholder: string
}[] = [
  {
    provider: 'anthropic',
    keyField: 'anthropic_api_key',
    keySetField: 'anthropic_api_key_set',
    modelField: 'llm_model',
    placeholder: 'sk-ant-…',
  },
  {
    provider: 'google',
    keyField: 'gemini_api_key',
    keySetField: 'gemini_api_key_set',
    modelField: 'gemini_model',
    placeholder: 'AIza…',
  },
  {
    provider: 'groq',
    keyField: 'groq_api_key',
    keySetField: 'groq_api_key_set',
    modelField: 'groq_model',
    placeholder: 'gsk_…',
  },
  {
    provider: 'inception',
    keyField: 'inception_api_key',
    keySetField: 'inception_api_key_set',
    modelField: 'inception_model',
    placeholder: 'sk_…',
  },
]

/** Upload / replace / remove the logo or the signature printed on documents. */
function CompanyImage({ kind, imageId }: { kind: 'logo' | 'signature'; imageId: number | null }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const { set, clear } = useCompanyImage(kind)
  return (
    <Space align="center">
      {imageId ? (
        <Image src={imageUrl(imageId)} height={48} style={{ objectFit: 'contain' }} />
      ) : (
        <Typography.Text type="secondary">{t('settings.noImage')}</Typography.Text>
      )}
      <Upload
        accept=".png,.jpg,.jpeg,.webp"
        showUploadList={false}
        beforeUpload={(file) => {
          set.mutate(file, { onError: (err) => message.error(errorMessage(t, err)) })
          return Upload.LIST_IGNORE
        }}
      >
        <Button size="small" icon={<UploadOutlined />} loading={set.isPending}>
          {imageId ? t('settings.replaceImage') : t('settings.uploadImage')}
        </Button>
      </Upload>
      {imageId && (
        <Button size="small" type="link" danger onClick={() => clear.mutate()}>
          {t('common.delete')}
        </Button>
      )}
    </Space>
  )
}

function GeneralTab() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const settings = useSettings()
  const save = useSaveSettings()
  const [form] = Form.useForm<FormValues>()
  const provider = Form.useWatch('llm_provider', form) ?? settings.data?.llm_provider

  useEffect(() => {
    if (settings.data) {
      form.setFieldsValue({
        ...settings.data,
        anthropic_api_key: undefined,
        gemini_api_key: undefined,
        groq_api_key: undefined,
        inception_api_key: undefined,
      })
    }
  }, [settings.data, form])

  const persist = async (values: FormValues) => {
    if (!settings.data) return
    const { anthropic_api_key, gemini_api_key, groq_api_key, inception_api_key, ...rest } = values
    await save.mutateAsync({
      ...settings.data,
      ...rest,
      company: { ...settings.data.company, ...rest.company },
      // blank field = keep the stored key
      anthropic_api_key: anthropic_api_key || undefined,
      gemini_api_key: gemini_api_key || undefined,
      groq_api_key: groq_api_key || undefined,
      inception_api_key: inception_api_key || undefined,
    })
    form.setFieldsValue({
      anthropic_api_key: undefined,
      gemini_api_key: undefined,
      groq_api_key: undefined,
      inception_api_key: undefined,
    })
  }

  const submit = async (values: FormValues) => {
    try {
      await persist(values)
      message.success(t('common.saved'))
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  const testLlm = useTestLlm()
  const runTest = async () => {
    try {
      // test what is on screen: a key just pasted or a provider just switched
      await persist(await form.validateFields())
      const res = await testLlm.mutateAsync()
      if (res.ok) message.success(t('settings.test_ok', { model: res.model }))
      else message.error(t(`settings.test_fail.${res.detail}`, { defaultValue: res.detail }))
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  const removeKey = async (field: keyof ApiKeysIn) => {
    if (!settings.data) return
    await save.mutateAsync({ ...settings.data, [field]: '' })
    message.success(t('common.saved'))
  }

  const keyStatus = (isSet: boolean | undefined, field: keyof ApiKeysIn) =>
    isSet ? (
      <Space>
        <Tag color="green">{t('settings.api_key_set')}</Tag>
        <Button size="small" type="link" danger onClick={() => void removeKey(field)}>
          {t('settings.api_key_remove')}
        </Button>
      </Space>
    ) : (
      <Tag>{t('settings.api_key_missing')}</Tag>
    )

  const testButton = (
    <Button
      size="small"
      style={{ marginTop: 6 }}
      loading={testLlm.isPending || save.isPending}
      onClick={() => void runTest()}
    >
      {t('settings.test')}
    </Button>
  )

  return (
    <Form form={form} layout="vertical" onFinish={submit} style={{ maxWidth: 860 }}>
      <Card title={t('settings.quoting')} size="small">
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <Form.Item
              name="offer_prefix"
              label={t('settings.offer_prefix')}
              rules={[{ required: true }]}
            >
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="default_margin_pct" label={t('settings.default_margin_pct')}>
              <InputNumber<string> stringMode addonAfter="%" style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="default_validity_days" label={t('settings.default_validity_days')}>
              <InputNumber min={1} precision={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="default_fx_rate_cny_usd" label={t('settings.default_fx_rate')}>
              <InputNumber<string> stringMode min="0" step="0.0001" style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item
              name="rounding"
              label={t('settings.rounding')}
              tooltip={t('settings.roundingHelp')}
            >
              <InputNumber min={0} max={4} precision={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
      </Card>

      <Card title={t('settings.ai')} size="small" style={{ marginTop: 16 }}>
        <Form.Item
          name="llm_provider"
          label={t('settings.provider')}
          extra={provider === 'inception' ? t('settings.provider_inception_hint') : undefined}
        >
          <Radio.Group
            optionType="button"
            options={PROVIDERS.map((p) => ({
              value: p.provider,
              label: t(`settings.provider_${p.provider}`),
            }))}
          />
        </Form.Item>
        {PROVIDERS.map((p) => (
          <Row gutter={16} key={p.provider} hidden={provider !== p.provider}>
            <Col xs={24} md={12}>
              <Form.Item
                name={p.keyField}
                label={t('settings.api_key')}
                hidden={provider !== p.provider}
                extra={keyStatus(settings.data?.[p.keySetField], p.keyField)}
              >
                <Input.Password autoComplete="off" placeholder={p.placeholder} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item
                name={p.modelField}
                label={t('settings.llm_model')}
                hidden={provider !== p.provider}
                rules={[{ required: true }]}
                extra={testButton}
              >
                <Input />
              </Form.Item>
            </Col>
          </Row>
        ))}
      </Card>

      <Card title={t('settings.company')} size="small" style={{ marginTop: 16 }}>
        <Row gutter={16}>
          {(['name_en', 'name_zh', 'address_en', 'address_zh', 'phone', 'email'] as const).map(
            (key) => (
              <Col xs={24} md={12} key={key}>
                <Form.Item name={['company', key]} label={t(`settings.company_${key}`)}>
                  <Input />
                </Form.Item>
              </Col>
            ),
          )}
          <Col xs={24} md={12}>
            <Form.Item label={t('settings.logo')} extra={t('settings.logoHelp')}>
              <CompanyImage kind="logo" imageId={settings.data?.company.logo_image_id ?? null} />
            </Form.Item>
          </Col>
        </Row>
      </Card>

      <Card title={t('settings.bank')} size="small" style={{ marginTop: 16 }}>
        <Typography.Paragraph type="secondary">{t('settings.bankHelp')}</Typography.Paragraph>
        <Row gutter={16}>
          {(['bank_account_name', 'bank_account_no', 'bank_name', 'bank_swift'] as const).map(
            (key) => (
              <Col xs={24} md={12} key={key}>
                <Form.Item name={['company', key]} label={t(`settings.company_${key}`)}>
                  <Input />
                </Form.Item>
              </Col>
            ),
          )}
          {(['seller_name', 'seller_phone', 'seller_email'] as const).map((key) => (
            <Col xs={24} md={8} key={key}>
              <Form.Item name={['company', key]} label={t(`settings.company_${key}`)}>
                <Input />
              </Form.Item>
            </Col>
          ))}
          <Col xs={24} md={12}>
            <Form.Item label={t('settings.signature')} extra={t('settings.signatureHelp')}>
              <CompanyImage
                kind="signature"
                imageId={settings.data?.company.signature_image_id ?? null}
              />
            </Form.Item>
          </Col>
        </Row>
      </Card>

      <Card title={t('settings.proforma')} size="small" style={{ marginTop: 16 }}>
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <Form.Item
              name="pi_prefix"
              label={t('settings.pi_prefix')}
              rules={[{ required: true }]}
            >
              <Input />
            </Form.Item>
          </Col>
          <Col xs={24} md={8}>
            <Form.Item name="price_age_warning_days" label={t('settings.price_age_warning_days')}>
              <InputNumber
                min={1}
                precision={0}
                addonAfter={t('quote.days')}
                style={{ width: '100%' }}
              />
            </Form.Item>
          </Col>
          {(['pi_payment_term', 'pi_lead_time', 'pi_delivery_place', 'pi_warranty'] as const).map(
            (key) => (
              <Col span={24} key={key}>
                <Form.Item
                  name={key}
                  label={t(`settings.${key}`)}
                  extra={key === 'pi_payment_term' ? t('settings.pi_payment_termHelp') : undefined}
                >
                  <Input.TextArea autoSize={{ minRows: 1, maxRows: 4 }} />
                </Form.Item>
              </Col>
            ),
          )}
        </Row>
      </Card>

      <Button type="primary" htmlType="submit" loading={save.isPending} style={{ marginTop: 16 }}>
        {t('common.save')}
      </Button>
    </Form>
  )
}

type CategoryFormValues = Omit<Category, 'attribute_schema'> & {
  attribute_schema: (Omit<AttributeField, 'options'> & { options?: string[] })[]
}

function CategoryDrawer({
  category,
  open,
  onClose,
}: {
  category: Category | null
  open: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [form] = Form.useForm<CategoryFormValues>()
  const save = useSaveCategory()

  useEffect(() => {
    if (!open) return
    form.resetFields()
    form.setFieldsValue(
      category
        ? {
            ...category,
            attribute_schema: category.attribute_schema.map((f) => ({
              ...f,
              options: f.options ?? undefined,
            })),
          }
        : { is_main: false, sort_order: 100, attribute_schema: [] },
    )
  }, [open, category, form])

  const submit = async (values: CategoryFormValues) => {
    const body: Partial<Category> = {
      ...values,
      attribute_schema: (values.attribute_schema ?? []).map((f) => ({
        ...f,
        in_fingerprint: Boolean(f.in_fingerprint),
        options: f.options?.length ? f.options : null,
      })),
    }
    if (category) delete body.code
    try {
      await save.mutateAsync({ id: category?.id, body })
      message.success(t('common.saved'))
      onClose()
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={960}
      title={category ? t('category.edit') : t('category.new')}
      destroyOnHidden
      extra={
        <Space>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="primary" loading={save.isPending} onClick={() => form.submit()}>
            {t('common.save')}
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical" onFinish={submit}>
        <Row gutter={16}>
          <Col span={6}>
            <Form.Item
              name="code"
              label={t('category.code')}
              rules={[{ required: true, pattern: /^[a-z][a-z0-9_]*$/ }]}
            >
              <Input disabled={Boolean(category)} />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item name="name_zh" label={t('category.name_zh')} rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item name="name_en" label={t('category.name_en')} rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item name="default_margin_pct" label={t('category.default_margin')}>
              <InputNumber<string> stringMode addonAfter="%" style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item name="is_main" label={t('category.is_main')} valuePropName="checked">
              <Switch />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item name="sort_order" label={t('category.sort_order')}>
              <InputNumber precision={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
        <Typography.Title level={5}>{t('category.schema')}</Typography.Title>
        <div className="qd-muted" style={{ marginBottom: 12 }}>
          {t('category.schemaHelp')}
        </div>
        <Form.List name="attribute_schema">
          {(fields, { add, remove, move }) => (
            <>
              {fields.map((field, index) => (
                <Row gutter={8} key={field.key} align="middle">
                  <Col span={4}>
                    <Form.Item
                      name={[field.name, 'key']}
                      rules={[{ required: true, pattern: /^[a-z][a-z0-9_]*$/ }]}
                    >
                      <Input placeholder={t('category.attrKey')} />
                    </Form.Item>
                  </Col>
                  <Col span={4}>
                    <Form.Item name={[field.name, 'label_zh']} rules={[{ required: true }]}>
                      <Input placeholder={t('category.attrLabelZh')} />
                    </Form.Item>
                  </Col>
                  <Col span={4}>
                    <Form.Item name={[field.name, 'label_en']} rules={[{ required: true }]}>
                      <Input placeholder={t('category.attrLabelEn')} />
                    </Form.Item>
                  </Col>
                  <Col span={3}>
                    <Form.Item name={[field.name, 'type']} initialValue="text">
                      <Select
                        options={ATTRIBUTE_TYPES.map((v) => ({
                          value: v,
                          label: t(`attrType.${v}`),
                        }))}
                      />
                    </Form.Item>
                  </Col>
                  <Col span={2}>
                    <Form.Item name={[field.name, 'unit']}>
                      <Input placeholder={t('category.attrUnit')} />
                    </Form.Item>
                  </Col>
                  <Col span={4}>
                    <Form.Item name={[field.name, 'options']}>
                      <Select
                        mode="tags"
                        maxTagCount="responsive"
                        placeholder={t('category.attrOptions')}
                      />
                    </Form.Item>
                  </Col>
                  <Col span={1}>
                    <Form.Item
                      name={[field.name, 'in_fingerprint']}
                      valuePropName="checked"
                      tooltip={t('category.inFingerprint')}
                    >
                      <Switch size="small" />
                    </Form.Item>
                  </Col>
                  <Col span={2}>
                    <Form.Item>
                      <Space size={0}>
                        <Button
                          type="text"
                          size="small"
                          disabled={index === 0}
                          onClick={() => move(index, index - 1)}
                          aria-label={t('common.moveUp')}
                        >
                          ↑
                        </Button>
                        <Button
                          type="text"
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() => remove(field.name)}
                          aria-label={t('common.remove')}
                        />
                      </Space>
                    </Form.Item>
                  </Col>
                </Row>
              ))}
              <Button
                type="dashed"
                icon={<PlusOutlined />}
                onClick={() => add({ type: 'text', in_fingerprint: false })}
              >
                {t('category.addAttr')}
              </Button>
              <div className="qd-muted" style={{ marginTop: 8 }}>
                {t('category.fingerprintColumnHelp')}
              </div>
            </>
          )}
        </Form.List>
      </Form>
    </Drawer>
  )
}

function CategoriesTab() {
  const { t, i18n } = useTranslation()
  const categories = useCategories()
  const [editing, setEditing] = useState<Category | null>(null)
  const [open, setOpen] = useState(false)

  return (
    <>
      <Button
        type="primary"
        icon={<PlusOutlined />}
        style={{ marginBottom: 12 }}
        onClick={() => {
          setEditing(null)
          setOpen(true)
        }}
      >
        {t('category.new')}
      </Button>
      <Table<Category>
        rowKey="id"
        size="small"
        loading={categories.isLoading}
        dataSource={categories.data}
        pagination={false}
        columns={[
          { title: t('category.name'), render: (_, c) => localName(c, i18n.language) },
          { title: t('category.code'), dataIndex: 'code' },
          {
            title: t('category.kind'),
            dataIndex: 'is_main',
            render: (v: boolean) =>
              v ? <Tag color="blue">{t('category.main')}</Tag> : <Tag>{t('category.extra')}</Tag>,
          },
          {
            title: t('category.schema'),
            render: (_, c) =>
              c.attribute_schema.map((f) => (
                <Tag key={f.key} color={f.in_fingerprint ? 'geekblue' : undefined}>
                  {i18n.language === 'en' ? f.label_en : f.label_zh}
                </Tag>
              )),
          },
          {
            title: t('category.default_margin'),
            dataIndex: 'default_margin_pct',
            render: (v: string | null) => (v ? `${v}%` : '—'),
          },
          { title: t('category.products'), dataIndex: 'product_count', align: 'right' },
          {
            render: (_, c) => (
              <Button
                type="link"
                onClick={() => {
                  setEditing(c)
                  setOpen(true)
                }}
              >
                {t('common.edit')}
              </Button>
            ),
          },
        ]}
      />
      <CategoryDrawer category={editing} open={open} onClose={() => setOpen(false)} />
    </>
  )
}

function AliasAdder({ brand }: { brand: Brand }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const { addAlias } = useBrandMutations()
  const [value, setValue] = useState('')
  const submit = async () => {
    const alias = value.trim()
    if (!alias) return
    try {
      const lang = /[一-鿿]/.test(alias) ? 'zh' : 'en'
      await addAlias.mutateAsync({ id: brand.id, alias, lang })
      setValue('')
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }
  return (
    <Input
      size="small"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onPressEnter={() => void submit()}
      placeholder={t('brand.aliasPlaceholder')}
      style={{ width: 140 }}
      suffix={<PlusOutlined onClick={() => void submit()} style={{ cursor: 'pointer' }} />}
    />
  )
}

function BrandsTab() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const brands = useBrands()
  const { create, remove, removeAlias } = useBrandMutations()
  const [filter, setFilter] = useState('')
  const [form] = Form.useForm<{ canonical: string; name_zh?: string }>()

  const add = async (values: { canonical: string; name_zh?: string }) => {
    try {
      await create.mutateAsync(values)
      form.resetFields()
      message.success(t('common.saved'))
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  const needle = filter.trim().toLowerCase()
  const rows = (brands.data ?? []).filter(
    (b) =>
      !needle ||
      b.canonical.toLowerCase().includes(needle) ||
      b.aliases.some((a) => a.alias.toLowerCase().includes(needle)),
  )

  return (
    <>
      <Space wrap style={{ marginBottom: 12, width: '100%', justifyContent: 'space-between' }}>
        <Form form={form} layout="inline" onFinish={add}>
          <Form.Item name="canonical" rules={[{ required: true, whitespace: true }]}>
            <Input placeholder={t('brand.canonical')} />
          </Form.Item>
          <Form.Item name="name_zh">
            <Input placeholder={t('brand.name_zh')} />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            icon={<PlusOutlined />}
            loading={create.isPending}
          >
            {t('brand.new')}
          </Button>
        </Form>
        <Input.Search
          allowClear
          placeholder={t('common.search')}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          style={{ width: 220 }}
        />
      </Space>
      <div className="qd-muted" style={{ marginBottom: 12 }}>
        {t('brand.help')}
      </div>
      <Table<Brand>
        rowKey="id"
        size="small"
        loading={brands.isLoading}
        dataSource={rows}
        pagination={{ pageSize: 50, hideOnSinglePage: true }}
        columns={[
          {
            title: t('brand.canonical'),
            dataIndex: 'canonical',
            width: 180,
            render: (v: string, b) => (
              <span>
                {v} {b.needs_review && <Tag color="orange">{t('brand.needsReview')}</Tag>}
              </span>
            ),
          },
          { title: t('brand.name_zh'), dataIndex: 'name_zh', width: 120 },
          {
            title: t('brand.aliases'),
            render: (_, b) => (
              <Space size={[4, 4]} wrap>
                {b.aliases.map((a) => (
                  <Tag
                    key={a.id}
                    closable
                    onClose={(e) => {
                      e.preventDefault()
                      removeAlias.mutate({ id: b.id, aliasId: a.id })
                    }}
                  >
                    {a.alias}
                  </Tag>
                ))}
                <AliasAdder brand={b} />
              </Space>
            ),
          },
          { title: t('brand.products'), dataIndex: 'product_count', align: 'right', width: 90 },
          {
            width: 60,
            render: (_, b) => (
              <Popconfirm
                title={t('brand.deleteConfirm', { name: b.canonical })}
                onConfirm={async () => {
                  try {
                    await remove.mutateAsync(b.id)
                  } catch (err) {
                    message.error(errorMessage(t, err))
                  }
                }}
              >
                <Button
                  type="text"
                  danger
                  size="small"
                  icon={<DeleteOutlined />}
                  disabled={b.product_count > 0}
                  aria-label={t('common.delete')}
                />
              </Popconfirm>
            ),
          },
        ]}
      />
    </>
  )
}

export default function Settings() {
  const { t } = useTranslation()
  return (
    <>
      <Typography.Title level={3}>{t('nav.settings')}</Typography.Title>
      <Tabs
        items={[
          { key: 'general', label: t('settings.tabs.general'), children: <GeneralTab /> },
          { key: 'categories', label: t('settings.tabs.categories'), children: <CategoriesTab /> },
          { key: 'brands', label: t('settings.tabs.brands'), children: <BrandsTab /> },
          { key: 'notes', label: t('settings.tabs.noteRules'), children: <NoteRulesTab /> },
          { key: 'backups', label: t('settings.tabs.backups'), children: <BackupsTab /> },
        ]}
      />
    </>
  )
}
