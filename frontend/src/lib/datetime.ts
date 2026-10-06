import dayjs from 'dayjs'

/** Local date and time, e.g. 2026-10-04 14:32. */
export function formatDateTime(value: string | null | undefined): string {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : ''
}
