import { InboxOutlined } from '@ant-design/icons'
import { App, Card, Table, Typography, Upload } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'

import { uploadImport, useImports, type ImportRecord } from '../api/imports'
import { ImportStatusTag } from '../components/import/labels'
import { errorMessage } from '../lib/i18n-helpers'

const ACCEPT = '.xlsx,.xlsm,.csv,.png,.jpg,.jpeg,.webp,.pdf'

export default function Imports() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const imports = useImports()
  const [uploading, setUploading] = useState(false)

  const send = async (files: File[]) => {
    setUploading(true)
    try {
      const record = await uploadImport(files)
      navigate(`/imports/${record.id}`)
    } catch (err) {
      message.error(errorMessage(t, err))
    } finally {
      setUploading(false)
    }
  }

  return (
    <>
      <Typography.Title level={3}>{t('nav.imports')}</Typography.Title>
      <Card style={{ marginBottom: 16 }}>
        <Upload.Dragger
          accept={ACCEPT}
          multiple
          showUploadList={false}
          disabled={uploading}
          beforeUpload={(file, fileList) => {
            // called once per file: send the whole selection as one import, once
            if (file === fileList[0]) void send(fileList)
            return Upload.LIST_IGNORE
          }}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">
            {uploading ? t('imports.uploading') : t('imports.dropHere')}
          </p>
          <p className="ant-upload-hint">{t('imports.dropHint')}</p>
        </Upload.Dragger>
      </Card>
      <Table<ImportRecord>
        rowKey="id"
        size="middle"
        loading={imports.isLoading}
        dataSource={imports.data}
        pagination={{ pageSize: 20, hideOnSinglePage: true }}
        locale={{ emptyText: t('imports.empty') }}
        columns={[
          {
            title: t('imports.file'),
            dataIndex: 'filename',
            render: (v: string, r) => <Link to={`/imports/${r.id}`}>{v}</Link>,
          },
          {
            title: t('imports.statusCol'),
            dataIndex: 'status',
            width: 120,
            render: (_, r) => <ImportStatusTag status={r.status} />,
          },
          {
            title: t('imports.result'),
            key: 'stats',
            render: (_, r) =>
              r.stats.committed
                ? t('review.committedSummary', r.stats.committed)
                : r.stats.total !== undefined
                  ? t('imports.rowsFound', { count: r.stats.total })
                  : '—',
          },
          {
            title: t('imports.created'),
            dataIndex: 'created_at',
            width: 170,
            render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
          },
        ]}
      />
    </>
  )
}
