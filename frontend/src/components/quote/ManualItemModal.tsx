import { App, Checkbox, Col, Form, Input, InputNumber, Modal, Row, Select } from 'antd'
import { useTranslation } from 'react-i18next'

import { useCategories } from '../../api/hooks'
import type { ManualLineInput } from '../../api/quotes'
import { textToDescription } from '../../lib/description'
import { errorMessage, localName } from '../../lib/i18n-helpers'

interface Values {
  name: string
  description?: string
  model_no?: string
  material?: string
  qty: number
  cost_usd?: string
  unit_price?: string
  category_id?: number
  save_to_catalog: boolean
}

/** An extra component typed by hand (camera, bag, service…), optionally kept in the catalog. */
export default function ManualItemModal({
  sectionId,
  onAdd,
  onClose,
}: {
  sectionId: number
  onAdd: (body: ManualLineInput) => Promise<unknown>
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const { message } = App.useApp()
  const categories = useCategories()
  const [form] = Form.useForm<Values>()
  const save = Form.useWatch('save_to_catalog', form)

  const submit = async () => {
    const v = await form.validateFields()
    try {
      await onAdd({
        section_id: sectionId,
        name: v.name,
        description_lines: textToDescription(v.description ?? ''),
        model_no: v.model_no || null,
        material: v.material || null,
        qty: v.qty,
        cost_usd: v.cost_usd ?? null,
        unit_price: v.unit_price ?? null,
        category_id: v.category_id ?? null,
        save_to_catalog: v.save_to_catalog,
      })
      onClose()
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  return (
    <Modal
      open
      width={640}
      title={t('quote.addManual')}
      onCancel={onClose}
      onOk={() => void submit()}
      okText={t('quote.add')}
    >
      <Form<Values> form={form} layout="vertical" initialValues={{ qty: 1, save_to_catalog: true }}>
        <Form.Item name="name" label={t('quote.name')} rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item
          name="description"
          label={t('quote.description')}
          extra={t('quote.descriptionHelp')}
        >
          <Input.TextArea autoSize={{ minRows: 3, maxRows: 10 }} />
        </Form.Item>
        <Row gutter={12}>
          <Col span={12}>
            <Form.Item name="model_no" label={t('quote.modelNo')}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="material" label={t('quote.material')}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="qty" label={t('quote.qty')} rules={[{ required: true }]}>
              <InputNumber min={1} precision={0} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="cost_usd" label={t('quote.cost')} extra={t('quote.costHelp')}>
              <InputNumber<string> stringMode min="0" prefix="$" style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              name="unit_price"
              label={t('quote.unitPrice')}
              extra={t('quote.unitPriceHelp')}
            >
              <InputNumber<string> stringMode min="0" prefix="$" style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="save_to_catalog" valuePropName="checked">
          <Checkbox>{t('quote.saveToCatalog')}</Checkbox>
        </Form.Item>
        <Form.Item
          name="category_id"
          label={t('product.category')}
          rules={[{ required: Boolean(save), message: t('quote.categoryNeeded') }]}
        >
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            options={(categories.data ?? []).map((c) => ({
              value: c.id,
              label: localName(c, i18n.language),
            }))}
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}
