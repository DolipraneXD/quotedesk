import { CloudUploadOutlined, DownloadOutlined, SaveOutlined } from '@ant-design/icons'
import {
  Alert,
  App,
  Button,
  Card,
  Form,
  InputNumber,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'
import { useTranslation } from 'react-i18next'

import { backupDownloadUrl, useBackupActions, useBackups, type Backup } from '../../api/backups'
import { useSaveSettings, useSettings } from '../../api/hooks'
import { formatDateTime } from '../../lib/datetime'
import { errorMessage } from '../../lib/i18n-helpers'

function size(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** Copies of the data: one on every start, more on demand; restore any of them. */
export default function BackupsTab() {
  const { t } = useTranslation()
  const { message, modal } = App.useApp()
  const backups = useBackups()
  const actions = useBackupActions()
  const settings = useSettings()
  const saveSettings = useSaveSettings()

  const run = async (fn: () => Promise<unknown>, done?: string) => {
    try {
      await fn()
      if (done) message.success(done)
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  const restore = (backup: Backup) =>
    modal.confirm({
      title: t('backup.restoreTitle', { name: backup.name }),
      content: backup.kind === 'full' ? t('backup.restoreFullHelp') : t('backup.restoreHelp'),
      okText: t('backup.restore'),
      okButtonProps: { danger: true },
      cancelText: t('common.cancel'),
      onOk: () =>
        run(async () => {
          const safety = await actions.restore.mutateAsync(backup.name)
          message.success(t('backup.restored', { safety: safety?.name ?? '—' }), 8)
        }),
    })

  return (
    <div style={{ maxWidth: 960 }}>
      <Typography.Paragraph type="secondary">{t('backup.help')}</Typography.Paragraph>
      <Space wrap style={{ marginBottom: 16 }}>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={actions.create.isPending && actions.create.variables === false}
          onClick={() => void run(() => actions.create.mutateAsync(false), t('backup.created'))}
        >
          {t('backup.createDb')}
        </Button>
        <Button
          icon={<SaveOutlined />}
          loading={actions.create.isPending && actions.create.variables === true}
          onClick={() => void run(() => actions.create.mutateAsync(true), t('backup.created'))}
        >
          {t('backup.createFull')}
        </Button>
        <Upload
          accept=".db,.zip"
          showUploadList={false}
          beforeUpload={(file) => {
            void run(() => actions.upload.mutateAsync(file), t('backup.uploaded'))
            return Upload.LIST_IGNORE
          }}
        >
          <Button icon={<CloudUploadOutlined />} loading={actions.upload.isPending}>
            {t('backup.upload')}
          </Button>
        </Upload>
      </Space>
      <Alert type="info" showIcon style={{ marginBottom: 16 }} message={t('backup.keysNote')} />
      <Table<Backup>
        rowKey="name"
        size="small"
        loading={backups.isLoading}
        dataSource={backups.data ?? []}
        pagination={{ pageSize: 20, hideOnSinglePage: true }}
        locale={{ emptyText: t('backup.empty') }}
        columns={[
          {
            title: t('backup.name'),
            dataIndex: 'name',
            render: (name: string, b) => (
              <Space size={4}>
                <span>{name}</span>
                <Tag color={b.kind === 'full' ? 'blue' : undefined}>
                  {t(`backup.kinds.${b.kind}`)}
                </Tag>
              </Space>
            ),
          },
          {
            title: t('backup.date'),
            dataIndex: 'created_at',
            width: 180,
            render: (v: string) => formatDateTime(v),
          },
          { title: t('backup.size'), dataIndex: 'size', width: 100, align: 'right', render: size },
          {
            key: 'actions',
            width: 260,
            render: (_, b) => (
              <Space size={4}>
                <Button size="small" icon={<DownloadOutlined />} href={backupDownloadUrl(b.name)}>
                  {t('backup.download')}
                </Button>
                <Button size="small" danger onClick={() => restore(b)}>
                  {t('backup.restore')}
                </Button>
                <Popconfirm
                  title={t('backup.deleteConfirm')}
                  onConfirm={() => void run(() => actions.remove.mutateAsync(b.name))}
                >
                  <Button size="small" type="text" danger>
                    {t('common.delete')}
                  </Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      {settings.data && (
        <Card size="small" style={{ marginTop: 16 }}>
          <Form
            layout="inline"
            initialValues={{ backup_retention: settings.data.backup_retention }}
            onFinish={(v: { backup_retention: number }) =>
              void run(
                () => saveSettings.mutateAsync({ ...settings.data!, ...v }),
                t('common.saved'),
              )
            }
          >
            <Form.Item
              name="backup_retention"
              label={t('backup.retention')}
              tooltip={t('backup.retentionHelp')}
            >
              <InputNumber min={1} max={365} precision={0} />
            </Form.Item>
            <Button htmlType="submit" loading={saveSettings.isPending}>
              {t('common.save')}
            </Button>
          </Form>
        </Card>
      )}
    </div>
  )
}
