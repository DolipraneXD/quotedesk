import { PlusOutlined } from '@ant-design/icons'
import { Button, Divider, Drawer, Select } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useCustomers, type Customer } from '../api/quotes'
import { CustomerForm } from './CustomerForm'

/**
 * Customer select for a Form.Item, with "New customer" at the foot of the list: the seller
 * adds a missing customer without leaving the quote, and it is picked once saved.
 */
export function CustomerPicker({
  value,
  onChange,
  onPick,
  disabled,
}: {
  value?: number | null
  onChange?: (id: number | undefined) => void
  /** The picked customer (also a newly created one, before the list refetches). */
  onPick?: (customer: Customer) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const customers = useCustomers()
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)

  const pick = (id: number | undefined) => {
    onChange?.(id)
    const customer = customers.data?.find((c) => c.id === id)
    if (customer) onPick?.(customer)
  }

  return (
    <>
      <Select
        allowClear
        showSearch
        disabled={disabled}
        value={value ?? undefined}
        onChange={pick}
        onSearch={setSearch}
        optionFilterProp="label"
        options={(customers.data ?? []).map((c) => ({
          value: c.id,
          label: `${c.code} · ${c.name}`,
        }))}
        popupRender={(menu) => (
          <>
            {menu}
            <Divider style={{ margin: '4px 0' }} />
            <Button
              type="text"
              block
              icon={<PlusOutlined />}
              style={{ textAlign: 'left' }}
              onClick={() => setCreating(true)}
            >
              {t('customer.new')}
            </Button>
          </>
        )}
      />
      <Drawer
        open={creating}
        width={560}
        title={t('customer.new')}
        onClose={() => setCreating(false)}
        destroyOnHidden
      >
        {creating && (
          <CustomerForm
            customer={null}
            initial={search.trim() ? { name: search.trim() } : undefined}
            onDone={(saved) => {
              setCreating(false)
              setSearch('')
              onChange?.(saved.id)
              onPick?.(saved)
            }}
          />
        )}
      </Drawer>
    </>
  )
}
