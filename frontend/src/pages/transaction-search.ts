// The transaction list's filters, as they live in the URL search params.
import type { TransactionQuery } from '@/api/hooks'

const PAGE_SIZE = 50

export type TransactionSearch = {
  from?: string
  to?: string
  category?: string
  merchant?: string
  personal?: boolean
  review?: boolean
  q?: string
  page?: number
}

const text = (v: unknown) => (typeof v === 'string' && v.trim() !== '' ? v : undefined)
const flag = (v: unknown) => (typeof v === 'boolean' ? v : undefined)
const isoDate = (v: unknown) => (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : undefined)

/** Anything odd in the URL is dropped instead of breaking the page. */
export function parseTransactionSearch(raw: Record<string, unknown>): TransactionSearch {
  const page = typeof raw.page === 'number' && raw.page > 1 ? Math.floor(raw.page) : undefined
  return {
    from: isoDate(raw.from),
    to: isoDate(raw.to),
    category: text(raw.category),
    merchant: text(raw.merchant),
    personal: flag(raw.personal),
    review: flag(raw.review),
    q: text(raw.q),
    page,
  }
}

export function toQuery(s: TransactionSearch): TransactionQuery {
  return {
    date_from: s.from,
    date_to: s.to,
    category: s.category,
    merchant: s.merchant,
    personal: s.personal,
    needs_review: s.review,
    q: s.q,
    page: s.page ?? 1,
    page_size: PAGE_SIZE,
  }
}
