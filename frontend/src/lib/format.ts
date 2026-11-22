// Formatting for display only. Amounts stay strings end to end, so no float ever touches money.

const CURRENCY_SIGN: Record<string, string> = { PLN: 'zł' }

/** "-1234.5" → "−1 234,50 zł" (Polish grouping and decimal comma). */
export function formatAmount(amount: string, currency = 'PLN'): string {
  const negative = amount.trim().startsWith('-')
  const [whole = '0', fraction = ''] = amount.trim().replace(/^[-+]/, '').split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
  const cents = fraction.padEnd(2, '0').slice(0, 2)
  return `${negative ? '−' : ''}${grouped},${cents} ${CURRENCY_SIGN[currency] ?? currency}`
}

export function isNegative(amount: string): boolean {
  return amount.trim().startsWith('-')
}

/** "2026-03-14" → "14.03.2026". */
export function formatDate(iso: string): string {
  const [year, month, day] = iso.split('-')
  return `${day}.${month}.${year}`
}

/** "0.930" → "93%". */
export function formatConfidence(confidence: string): string {
  return `${Math.round(Number(confidence) * 100)}%`
}
