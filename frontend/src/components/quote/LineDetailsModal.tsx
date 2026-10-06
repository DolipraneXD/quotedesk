import { CloseCircleFilled, PlusOutlined } from '@ant-design/icons'
import { App, Button, Checkbox, Col, Form, Image, Input, Modal, Row, Space, Typography } from 'antd'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

import { useProduct } from '../../api/hooks'
import { imageUrl, type LinePatch, type QuoteLine } from '../../api/quotes'
import { descriptionToText, textToDescription } from '../../lib/description'
import { errorMessage } from '../../lib/i18n-helpers'

interface Values {
  name: string
  name_emphasis: boolean
  description: string
  model_no: string | null
  material: string | null
  image_ids: number[]
}

export function DescriptionPreview({ lines }: { lines: QuoteLine['description_lines'] }) {
  return (
    <div className="qd-desc">
      {lines.map((d, i) => (
        <div key={i} className={d.emphasis ? 'qd-red' : undefined}>
          {d.text}
        </div>
      ))}
    </div>
  )
}

/** Everything printed for a line besides the numbers: name, specs, model, material, photos. */
export default function LineDetailsModal({
  line,
  readOnly,
  onSave,
  onClose,
}: {
  line: QuoteLine | null
  readOnly: boolean
  onSave: (patch: LinePatch) => Promise<unknown>
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [form] = Form.useForm<Values>()
  const product = useProduct(line?.product_id ?? 0)
  const description = Form.useWatch('description', form) ?? ''
  const imageIds = Form.useWatch('image_ids', form) ?? []

  useEffect(() => {
    if (line) {
      form.setFieldsValue({
        name: line.name,
        name_emphasis: line.name_emphasis,
        description: descriptionToText(line.description_lines),
        model_no: line.model_no,
        material: line.material,
        image_ids: line.image_ids,
      })
    }
  }, [line, form])

  if (!line) return null
  const productImages = line.product_id ? (product.data?.image_ids ?? []) : []
  const addable = productImages.filter((id) => !imageIds.includes(id))

  const submit = async () => {
    const values = await form.validateFields()
    try {
      await onSave({
        name: values.name,
        name_emphasis: values.name_emphasis,
        description_lines: textToDescription(values.description ?? ''),
        model_no: values.model_no || null,
        material: values.material || null,
        image_ids: values.image_ids,
      })
      onClose()
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  return (
    <Modal
      open
      width={760}
      title={t('quote.lineDetails')}
      onCancel={onClose}
      onOk={() => void submit()}
      okButtonProps={{ disabled: readOnly }}
      okText={t('common.save')}
    >
      <Form form={form} layout="vertical" disabled={readOnly}>
        <Row gutter={12}>
          <Col span={16}>
            <Form.Item name="name" label={t('quote.name')} rules={[{ required: true }]}>
              <Input.TextArea autoSize={{ minRows: 1, maxRows: 3 }} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="name_emphasis" valuePropName="checked" label=" ">
              <Checkbox>{t('quote.nameRed')}</Checkbox>
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="description"
              label={t('quote.description')}
              extra={t('quote.descriptionHelp')}
            >
              <Input.TextArea autoSize={{ minRows: 8, maxRows: 22 }} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Typography.Text type="secondary">{t('quote.preview')}</Typography.Text>
            <DescriptionPreview lines={textToDescription(description)} />
          </Col>
          <Col span={12}>
            <Form.Item name="model_no" label={t('quote.modelNo')}>
              <Input placeholder="DN11-116PC-HS-R52" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="material" label={t('quote.material')}>
              <Input placeholder="Plastic" />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="image_ids" label={t('quote.photos')} extra={t('quote.photosHelp')}>
          <PhotoChooser available={addable} readOnly={readOnly} />
        </Form.Item>
      </Form>
    </Modal>
  )
}

function PhotoChooser({
  value = [],
  onChange,
  available,
  readOnly,
}: {
  value?: number[]
  onChange?: (ids: number[]) => void
  available: number[]
  readOnly: boolean
}) {
  const { t } = useTranslation()
  return (
    <Space wrap align="start">
      {value.map((id) => (
        <div key={id} className="qd-thumb">
          <Image src={imageUrl(id)} width={96} height={72} style={{ objectFit: 'contain' }} />
          {!readOnly && (
            <CloseCircleFilled
              className="qd-thumb-remove"
              onClick={() => onChange?.(value.filter((v) => v !== id))}
            />
          )}
        </div>
      ))}
      {!readOnly &&
        available.map((id) => (
          <Button
            key={id}
            className="qd-thumb-add"
            onClick={() => onChange?.([...value, id])}
            title={t('quote.addPhoto')}
          >
            <img src={imageUrl(id)} alt="" />
            <PlusOutlined />
          </Button>
        ))}
      {!value.length && !available.length && (
        <Typography.Text type="secondary">{t('quote.noPhotos')}</Typography.Text>
      )}
    </Space>
  )
}
