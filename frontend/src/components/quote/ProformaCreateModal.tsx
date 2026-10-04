import { App, Checkbox, Form, Input, Modal, Space, Typography } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { useCreateProforma, type Quote } from '../../api/quotes'
import { errorMessage } from '../../lib/i18n-helpers'
import { formatUsd } from '../../lib/money'

/** A quote of alternatives usually becomes a proforma invoice for one build. */
export default function ProformaCreateModal({
  quote,
  onClose,
}: {
  quote: Quote
  onClose: () => void
}) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const create = useCreateProforma(quote.id)
  const [selected, setSelected] = useState<number[]>([])
  const [poNo, setPoNo] = useState('')

  const submit = async () => {
    try {
      const pi = await create.mutateAsync({ line_ids: selected, po_no: poNo || null })
      onClose()
      navigate(`/proformas/${pi.id}`)
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  return (
    <Modal
      open
      width={640}
      title={t('proforma.create')}
      onCancel={onClose}
      onOk={() => void submit()}
      okText={t('proforma.createOk')}
      okButtonProps={{ disabled: !selected.length }}
      confirmLoading={create.isPending}
    >
      <Typography.Paragraph type="secondary">{t('proforma.pickLines')}</Typography.Paragraph>
      <Checkbox.Group
        value={selected}
        onChange={(v) => setSelected(v as number[])}
        style={{ width: '100%' }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          {quote.sections.map((section, index) => (
            <div key={section.id}>
              <Typography.Text strong>
                {section.title || t('quote.sectionN', { n: index + 1 })}
              </Typography.Text>
              {section.lines.map((line) => (
                <div key={line.id} style={{ paddingLeft: 12 }}>
                  <Checkbox value={line.id}>
                    {line.printed_no}. {line.name}{' '}
                    <span className="qd-muted">
                      × {line.qty} · {formatUsd(line.total)}
                    </span>
                  </Checkbox>
                </div>
              ))}
            </div>
          ))}
        </Space>
      </Checkbox.Group>
      <Form layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item label={t('proforma.poNo')}>
          <Input value={poNo} onChange={(e) => setPoNo(e.target.value)} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
