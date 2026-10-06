import { Tag, Tooltip } from 'antd'
import { useTranslation } from 'react-i18next'

import type { ImportStatus, Issue, RowStatus } from '../../api/imports'
import { IMPORT_STATUS_COLORS, ROW_STATUS_COLORS, WARNING_ISSUES, issueText } from './importLabels'

export function ImportStatusTag({ status }: { status: ImportStatus }) {
  const { t } = useTranslation()
  return <Tag color={IMPORT_STATUS_COLORS[status]}>{t(`imports.status.${status}`)}</Tag>
}

export function RowStatusTag({ status }: { status: RowStatus }) {
  const { t } = useTranslation()
  return <Tag color={ROW_STATUS_COLORS[status]}>{t(`review.status.${status}`)}</Tag>
}

export function IssueTags({ issues }: { issues: { code: string }[] }) {
  const { t } = useTranslation()
  if (!issues.length) return null
  return (
    <>
      {issues.map((issue, i) => (
        <Tooltip key={i} title={issueText(t, issue as Issue)}>
          <Tag
            color={
              WARNING_ISSUES.has(issue.code) ? 'red' : issue.code === 'llm' ? 'default' : 'gold'
            }
            style={{ marginBottom: 2 }}
          >
            {t(`issues.short.${issue.code}`, { defaultValue: issue.code })}
          </Tag>
        </Tooltip>
      ))}
    </>
  )
}
