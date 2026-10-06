import { ArrowLeftOutlined } from '@ant-design/icons'
import { Alert, App, Button, Popconfirm, Result, Space, Spin, Steps, Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { useImport, useImportActions, type ImportStatus } from '../api/imports'
import ExtractProgress from '../components/import/ExtractProgress'
import ImportReview from '../components/import/ImportReview'
import { ImportStatusTag } from '../components/import/labels'
import SheetPicker from '../components/import/SheetPicker'
import { errorMessage } from '../lib/i18n-helpers'

const STEP: Record<ImportStatus, number> = {
  uploaded: 1,
  failed: 1,
  cancelled: 1,
  extracting: 2,
  review: 3,
  committed: 4,
  reverted: 4,
}

export default function ImportDetail() {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const id = Number(useParams().id)
  const imp = useImport(id)
  const actions = useImportActions(id)

  if (imp.isLoading) return <Spin />
  if (!imp.data) {
    return (
      <Result
        status="404"
        title={t('errors.import.not_found')}
        extra={<Link to="/imports">{t('common.back')}</Link>}
      />
    )
  }
  const record = imp.data

  const remove = async () => {
    try {
      await actions.remove.mutateAsync()
      navigate('/imports')
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  const revert = async () => {
    try {
      await actions.revert.mutateAsync()
      message.success(t('review.reverted'))
    } catch (err) {
      message.error(errorMessage(t, err))
    }
  }

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <Link to="/imports">
          <ArrowLeftOutlined /> {t('nav.imports')}
        </Link>
      </Space>
      <Space style={{ width: '100%', justifyContent: 'space-between' }} align="start" wrap>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>
            {record.filename}
          </Typography.Title>
          <Space style={{ marginTop: 8 }}>
            <ImportStatusTag status={record.status} />
            {record.llm_model === 'manual' ? (
              <span className="qd-muted">{t('mapping.byHand')}</span>
            ) : (
              record.llm_model && (
                <span className="qd-muted">
                  {record.llm_model} ·{' '}
                  {t('imports.tokens', {
                    input: record.llm_tokens_in,
                    output: record.llm_tokens_out,
                  })}
                </span>
              )
            )}
          </Space>
        </div>
        <Space>
          {record.status === 'committed' && (
            <Popconfirm title={t('review.revertConfirm')} onConfirm={() => void revert()}>
              <Button danger loading={actions.revert.isPending}>
                {t('review.revert')}
              </Button>
            </Popconfirm>
          )}
          {record.status !== 'committed' && record.status !== 'extracting' && (
            <Popconfirm title={t('imports.deleteConfirm')} onConfirm={() => void remove()}>
              <Button danger>{t('common.delete')}</Button>
            </Popconfirm>
          )}
        </Space>
      </Space>

      <Steps
        size="small"
        style={{ margin: '20px 0' }}
        current={STEP[record.status]}
        status={record.status === 'failed' ? 'error' : undefined}
        items={[
          { title: t('imports.steps.upload') },
          { title: t('imports.steps.sheets') },
          { title: t('imports.steps.extract') },
          { title: t('imports.steps.review') },
          { title: t('imports.steps.commit') },
        ]}
      />

      {record.status === 'failed' && record.error && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message={t('imports.failed')}
          description={record.error}
        />
      )}
      {record.status === 'cancelled' && (
        <Alert type="info" showIcon style={{ marginBottom: 16 }} message={t('imports.cancelled')} />
      )}

      {['uploaded', 'failed', 'cancelled'].includes(record.status) && (
        <SheetPicker record={record} />
      )}
      {record.status === 'extracting' && <ExtractProgress record={record} />}
      {['review', 'committed', 'reverted'].includes(record.status) && (
        <ImportReview record={record} />
      )}
    </>
  )
}
