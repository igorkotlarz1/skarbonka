// A small typed wrapper around fetch. The types come from `schema.ts`, which
// `npm run api:types` generates from the backend's OpenAPI schema.
import type { components } from './schema'

type Schemas = components['schemas']
export type Transaction = Schemas['TransactionOut']
export type Allocation = Schemas['AllocationOut']
export type TransactionPage = Schemas['TransactionPage']
export type Category = Schemas['CategoryOut']
export type AllocationPatch = Schemas['AllocationPatch']
export type BulkChange = Schemas['BulkChange']
export type BulkResult = Schemas['BulkResult']

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type Query = Record<string, string | number | boolean | undefined>

function url(path: string, query?: Query): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const search = params.toString()
  return search ? `${path}?${search}` : path
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const response = await fetch(url(path, query), {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const payload: unknown = await response.json()
      if (payload && typeof payload === 'object' && 'detail' in payload) {
        detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail)
      }
    } catch {
      // The body was not JSON; the status text is enough.
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>('GET', path, undefined, query),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  post: <T>(path: string, body: unknown) => request<T>('POST', path, body),
}
