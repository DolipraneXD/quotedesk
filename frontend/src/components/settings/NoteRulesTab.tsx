import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import {
  App,
  AutoComplete,
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Typography,
} from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useNoteRuleMutations, useNoteRules, type NoteRuleInput } from '../../api/hooks'
import type { NoteRule } from '../../api/types'
import { errorMessage } from '../../lib/i18n-helpers'

const KINDS = ['set', 'qty', 'text'] as const

/** Remark patterns (备注) that set product fields when a price list is imported. */
export default function NoteRulesTab() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const rules = useNoteRules()
  const { save, remove } = useNoteRuleMutations()
  const [editing, setEditing] = useState<NoteRule | 'new' | null>(null)
  const [form] = Form.useForm<NoteRuleInput>()
  const kind = Form.useWatch('kind', form)
  const fields = [...new Set((rules.data ?? []).map((r) => r.field))].sort()

  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn()
      return true
    } catch (err) {
      message.error(errorMessage(t, err))
      return false
    }
  }

  const open = (rule: NoteRule | 'new') => {
    setEditing(rule)
    form.setFieldsValue(
      rule === 'new' ? { pattern: '', field: '', kind: 'set', value: '' } : { ...rule },
    )
  }

  const submit = async () => {
    const values = await form.validateFields()
    const id = editing && editing !== 'new' ? editing.id : undefined
    const body = { ...values, value: values.kind === 'set' ? values.value : null }
    if (await run(() => save.mutateAsync({ id, ...body }))) setEditing(null)
  }

  return (
    <>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 12 }}>
        <span className="qd-muted">{t('noteRule.help')}</span>
        <Button icon={<PlusOutlined />} onClick={() => open('new')}>
          {t('noteRule.add')}
        </Button>
      </Space>
      <Table<NoteRule>
        rowKey="id"
        size="small"
        loading={rules.isLoading}
        dataSource={rules.data}
        pagination={false}
        columns={[
          {
            title: t('noteRule.pattern'),
            dataIndex: 'pattern',
            render: (v: string) => <Typography.Text code>{v}</Typography.Text>,
          },
          { title: t('noteRule.field'), dataIndex: 'field' },
          {
            title: t('noteRule.kind'),
            dataIndex: 'kind',
            render: (v: string) => t(`noteRule.kinds.${v}`),
          },
          { title: t('noteRule.value'), dataIndex: 'value' },
          {
            title: t('noteRule.enabled'),
            key: 'enabled',
            width: 90,
            render: (_, r) => (
              <Switch
                size="small"
                checked={r.enabled}
                onChange={(enabled) => void run(() => save.mutateAsync({ id: r.id, enabled }))}
              />
            ),
          },
          {
            key: 'actions',
            width: 90,
            render: (_, r) => (
              <Space size={0}>
                <Button size="small" type="text" icon={<EditOutlined />} onClick={() => open(r)} />
                <Popconfirm
                  title={t('noteRule.deleteConfirm')}
                  onConfirm={() => void run(() => remove.mutateAsync(r.id))}
                >
                  <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        open={editing !== null}
        title={editing === 'new' ? t('noteRule.add') : t('noteRule.edit')}
        okText={t('common.save')}
        cancelText={t('common.cancel')}
        confirmLoading={save.isPending}
        onOk={() => void submit()}
        onCancel={() => setEditing(null)}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="pattern"
            label={t('noteRule.pattern')}
            tooltip={t('noteRule.patternHelp')}
            rules={[{ required: true }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="field" label={t('noteRule.field')} rules={[{ required: true }]}>
            <AutoComplete options={fields.map((f) => ({ value: f }))} filterOption />
          </Form.Item>
          <Form.Item
            name="kind"
            label={t('noteRule.kind')}
            extra={kind && t(`noteRule.kindHelp.${kind}`)}
          >
            <Select options={KINDS.map((k) => ({ value: k, label: t(`noteRule.kinds.${k}`) }))} />
          </Form.Item>
          {kind === 'set' && (
            <Form.Item name="value" label={t('noteRule.value')} rules={[{ required: true }]}>
              <Input />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </>
  )
}
