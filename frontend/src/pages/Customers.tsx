import { PlusOutlined } from '@ant-design/icons'
import { App, Button, Drawer, Input, Popconfirm, Space, Table, Typography } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { useCustomers, useDeleteCustomer, type Customer } from '../api/quotes'
import { CustomerForm } from '../components/CustomerForm'
import { errorMessage } from '../lib/i18n-helpers'
import { useDebounced } from '../lib/useDebounced'

export default function Customers() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [search, setSearch] = useState('')
  const q = useDebounced(search, 250)
  const customers = useCustomers(q)
  const remove = useDeleteCustomer()
  const [editing, setEditing] = useState<Customer | null | undefined>(undefined)

  return (
    <>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {t('nav.customers')}
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditing(null)}>
          {t('customer.new')}
        </Button>
      </Space>
      <Input.Search
        allowClear
        placeholder={t('customer.search')}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ maxWidth: 360, marginBottom: 16 }}
      />
      <Table<Customer>
        rowKey="id"
        loading={customers.isLoading}
        dataSource={customers.data}
        pagination={{ pageSize: 50, hideOnSinglePage: true }}
        locale={{ emptyText: t('customer.empty') }}
        columns={[
          { title: t('customer.code'), dataIndex: 'code', width: 110 },
          {
            title: t('customer.name'),
            dataIndex: 'name',
            render: (name: string, c) => <a onClick={() => setEditing(c)}>{name}</a>,
          },
          { title: t('customer.contact_name'), dataIndex: 'contact_name', width: 140 },
          { title: t('customer.email'), dataIndex: 'email', width: 220 },
          { title: t('customer.trade_term'), dataIndex: 'trade_term', width: 150 },
          {
            title: t('customer.default_margin_pct'),
            dataIndex: 'default_margin_pct',
            width: 110,
            align: 'right',
            render: (v: string | null) => (v === null ? '—' : `${Number(v)}%`),
          },
          {
            key: 'actions',
            width: 160,
            render: (_, c) => (
              <Space>
                <Link to={`/quotes?customer=${c.id}`}>{t('nav.quotes')}</Link>
                <Popconfirm
                  title={t('customer.deleteConfirm', { name: c.name })}
                  onConfirm={async () => {
                    try {
                      await remove.mutateAsync(c.id)
                    } catch (err) {
                      message.error(errorMessage(t, err))
                    }
                  }}
                >
                  <a className="qd-danger">{t('common.delete')}</a>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      <Drawer
        open={editing !== undefined}
        width={560}
        title={editing ? editing.name : t('customer.new')}
        onClose={() => setEditing(undefined)}
        destroyOnHidden
      >
        {editing !== undefined && (
          <CustomerForm customer={editing} onDone={() => setEditing(undefined)} />
        )}
      </Drawer>
    </>
  )
}
