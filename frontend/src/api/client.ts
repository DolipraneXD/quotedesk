const BASE = '/api/v1'

/** An RFC 7807 problem from the backend. `key` is an i18n message key. */
export class ApiError extends Error {
  status: number
  key: string
  params: Record<string, unknown>

  constructor(status: number, key: string, detail: string, params: Record<string, unknown>) {
    super(detail)
    this.status = status
    this.key = key
    this.params = params
  }
}

type Query = Record<string, string | number | boolean | undefined | null>

function withQuery(path: string, query?: Query): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== '') params.set(k, String(v))
  }
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

export async function api<T>(
  method: string,
  path: string,
  options: { body?: unknown; query?: Query } = {},
): Promise<T> {
  const res = await fetch(BASE + withQuery(path, options.query), {
    method,
    headers: options.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  })
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    throw new ApiError(
      res.status,
      data?.key ?? 'error.unknown',
      data?.detail ?? res.statusText,
      data?.params ?? {},
    )
  }
  return data as T
}
