import { Alert, App, Form, Modal } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useMergeProduct } from '../api/hooks'
import type { Product } from '../api/types'
import { errorMessage } from '../lib/i18n-helpers'
import ProductPicker from './ProductPicker'

/** Merge `product` into another one. `product` is deleted; its history moves over. */
export default function MergeModal({
  product,
  open,
  onClose,
  onMerged,
}: {
  product: Product
  open: boolean
  onClose: () => void
  onMerged?: (kept: Product) => void
}) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [intoId, setIntoId] = useState<number>()
  const merge = useMergeProduct()

  const submit = async () => {
    if (!intoId) return
    try {
      const kept = await merge.mutateAsync({ id: product.id, intoId })
      message.success(t('product.merged'))
      onClose()
      onMerged?.(kept)
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  return (
    <Modal
      open={open}
      title={t('product.mergeInto')}
      okText={t('product.merge')}
      okButtonProps={{ danger: true, disabled: !intoId, loading: merge.isPending }}
      onOk={submit}
      onCancel={onClose}
      destroyOnHidden
    >
      <Alert type="warning" showIcon message={t('product.mergeHelp', { name: product.name_zh })} />
      <Form layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item label={t('product.mergeTarget')} required>
          <ProductPicker
            value={intoId}
            onChange={setIntoId}
            excludeId={product.id}
            categoryId={product.category_id}
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}
