import { CloseCircleFilled, UploadOutlined } from '@ant-design/icons'
import { App, Button, Card, Empty, Image, Popconfirm, Space, Upload } from 'antd'
import { useTranslation } from 'react-i18next'

import { imageUrl, useProductImages } from '../api/quotes'
import type { Product } from '../api/types'
import { errorMessage } from '../lib/i18n-helpers'

/** Photos printed in the Photo column of quote lists (the first two). */
export default function ProductPhotos({ product }: { product: Product }) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const { add, remove } = useProductImages(product.id)

  return (
    <Card
      title={t('product.photos')}
      style={{ marginTop: 16 }}
      extra={
        <Upload
          multiple
          accept=".png,.jpg,.jpeg,.webp"
          showUploadList={false}
          beforeUpload={(file, files) => {
            if (file === files[0]) {
              add.mutate(files, { onError: (err) => message.error(errorMessage(t, err)) })
            }
            return Upload.LIST_IGNORE
          }}
        >
          <Button size="small" icon={<UploadOutlined />} loading={add.isPending}>
            {t('product.addPhotos')}
          </Button>
        </Upload>
      }
    >
      {product.image_ids.length ? (
        <Image.PreviewGroup>
          <Space wrap>
            {product.image_ids.map((id) => (
              <div key={id} className="qd-thumb">
                <Image
                  src={imageUrl(id)}
                  width={120}
                  height={90}
                  style={{ objectFit: 'contain' }}
                />
                <Popconfirm title={t('product.removePhoto')} onConfirm={() => remove.mutate(id)}>
                  <CloseCircleFilled className="qd-thumb-remove" />
                </Popconfirm>
              </div>
            ))}
          </Space>
        </Image.PreviewGroup>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('product.noPhotos')} />
      )}
    </Card>
  )
}
