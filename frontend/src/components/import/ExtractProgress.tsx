import { Alert, Button, Card, Progress, Space, Typography } from 'antd'
import { useTranslation } from 'react-i18next'

import { useImportActions, type ImportRecord } from '../../api/imports'

export default function ExtractProgress({ record }: { record: ImportRecord }) {
  const { t } = useTranslation()
  const { cancel } = useImportActions(record.id)
  const p = record.progress
  const total = p.total_chunks ?? 0
  const done = p.done_chunks ?? 0
  const percent = total ? Math.round((done / total) * 100) : 0

  return (
    <Card>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Typography.Text strong>{t('imports.extracting')}</Typography.Text>
        <Progress percent={percent} status="active" />
        <div className="qd-muted">
          {total ? t('imports.chunks', { done, total }) : t('imports.preparing')} ·{' '}
          {t('imports.tokens', { input: record.llm_tokens_in, output: record.llm_tokens_out })}
        </div>
        {Object.entries(p.sheets ?? {}).map(([name, s]) => (
          <div key={name}>
            <div>{name}</div>
            <Progress
              size="small"
              percent={s.total ? Math.round((s.done / s.total) * 100) : 0}
              format={() => `${s.done}/${s.total}`}
            />
          </div>
        ))}
        {(p.errors ?? []).map((e, i) => (
          <Alert
            key={i}
            type="error"
            showIcon
            message={
              e.rows
                ? t('imports.chunkError', { sheet: e.sheet, rows: e.rows })
                : t('imports.sourceError', { sheet: e.sheet })
            }
            description={e.message}
          />
        ))}
        <Button danger onClick={() => cancel.mutate()} loading={cancel.isPending}>
          {t('imports.cancel')}
        </Button>
      </Space>
    </Card>
  )
}
