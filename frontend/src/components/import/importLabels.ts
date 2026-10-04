import type { TFunction } from 'i18next'

import type { ImportStatus, Issue, RowStatus } from '../../api/imports'

export const IMPORT_STATUS_COLORS: Record<ImportStatus, string> = {
  uploaded: 'default',
  extracting: 'processing',
  review: 'gold',
  committed: 'green',
  reverted: 'default',
  failed: 'red',
  cancelled: 'default',
}

export const ROW_STATUS_COLORS: Record<RowStatus, string> = {
  new: 'green',
  updated: 'blue',
  unchanged: 'default',
  possible_match: 'orange',
  problem: 'red',
}

/** Issue codes come from the backend with their parameters; unknown codes show raw. */
export function issueText(t: TFunction, issue: Issue): string {
  const key = `issues.${issue.code}`
  const text = t(key, issue)
  return text === key ? `${issue.code} ${JSON.stringify(issue)}` : text
}

export const WARNING_ISSUES = new Set([
  'price_swing',
  'older_price_date',
  'identity_changed',
  'duplicate_in_import',
  'erp_conflict',
  'commit_failed',
  'unknown_category',
  'missing_name',
  'invalid_attribute',
])
