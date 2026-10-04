import { PlusOutlined, WarningOutlined } from '@ant-design/icons'
import { App, Button, Form, Input, Modal, Space, Table, Tag, Tooltip, Typography } from 'antd'
import dayjs from 'dayjs'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'

import {
  useConfigurations,
  useCreateConfiguration,
  type ConfigurationSummary,
} from '../api/configurations'
import { imageUrl } from '../api/quotes'
import { errorMessage } from '../lib/i18n-helpers'
import { formatCost } from '../lib/money'
import { useDebounced } from '../lib/useDebounced'

/** Saved builds: what quotes insert as one combined product. */
export default function Configurations() {
  const { t, i18n } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const q = useDebounced(search, 250)
  const configs = useConfigurations(q)
  const create = useCreateConfiguration()
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm<{ name: string }>()

  const submit = async () => {
    const { name } = await form.validateFields()
    try {
      const config = await create.mutateAsync({ name })
      setCreating(false)
      navigate(`/configurations/${config.id}`)
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  return (
    <>
      <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {t('nav.configurations')}
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreating(true)}>
          {t('config.new')}
        </Button>
      </Space>
      <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
        {t('config.intro')}
      </Typography.Paragraph>
      <Input.Search
        allowClear
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder={t('config.searchPlaceholder')}
        style={{ maxWidth: 420, marginBottom: 16 }}
      />
      <Table<ConfigurationSummary>
        rowKey="id"
        size="small"
        loading={configs.isLoading}
        dataSource={configs.data ?? []}
        pagination={{ pageSize: 50, hideOnSinglePage: true }}
        locale={{ emptyText: t('config.empty') }}
        columns={[
          {
            key: 'photo',
            width: 64,
            render: (_, c) =>
              c.image_id && (
                <img
                  src={imageUrl(c.image_id)}
                  alt=""
                  style={{ width: 48, height: 40, objectFit: 'contain' }}
                />
              ),
          },
          {
            title: t('config.name'),
            key: 'name',
            render: (_, c) => (
              <div>
                <Link to={`/configurations/${c.id}`}>
                  {i18n.language === 'zh' && c.name_zh ? c.name_zh : c.name}
                </Link>
                {c.model_no && <div className="qd-muted">{c.model_no}</div>}
              </div>
            ),
          },
          { title: t('config.platform'), dataIndex: 'platform', width: 140 },
          { title: t('config.parts'), dataIndex: 'parts', width: 80, align: 'right' },
          {
            title: t('config.unitCost'),
            key: 'cost',
            width: 160,
            align: 'right',
            render: (_, c) => (
              <Space size={4}>
                {(c.cost_changed || c.missing_cost > 0) && (
                  <Tooltip
                    title={
                      <>
                        {c.cost_changed && (
                          <div>{t('config.costChanged', { was: formatCost(c.saved_cost) })}</div>
                        )}
                        {c.missing_cost > 0 && (
                          <div>{t('config.missingCost', { count: c.missing_cost })}</div>
                        )}
                      </>
                    }
                  >
                    <WarningOutlined style={{ color: '#d48806' }} />
                  </Tooltip>
                )}
                <span className="qd-money">{formatCost(c.unit_cost) || '—'}</span>
              </Space>
            ),
          },
          {
            title: t('config.usedIn'),
            dataIndex: 'used_in',
            width: 110,
            align: 'right',
            render: (n: number) => (n ? <Tag>{t('config.quotesCount', { count: n })}</Tag> : '—'),
          },
          {
            title: t('config.updated'),
            dataIndex: 'updated_at',
            width: 120,
            render: (v: string) => dayjs(v).format('YYYY-MM-DD'),
          },
        ]}
      />
      <Modal
        open={creating}
        title={t('config.new')}
        okText={t('common.create')}
        cancelText={t('common.cancel')}
        confirmLoading={create.isPending}
        onOk={() => void submit()}
        onCancel={() => setCreating(false)}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item name="name" label={t('config.name')} rules={[{ required: true }]}>
            <Input autoFocus onPressEnter={() => void submit()} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
