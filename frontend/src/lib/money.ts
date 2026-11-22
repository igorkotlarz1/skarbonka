// Split arithmetic in whole grosze (integers), so 0.1 + 0.2 never becomes 0.30000000000000004.

/** "12,30", "12.3", "-12.30" → 1230 or -1230; null when it is not an amount. */
export function toGrosze(text: string): number | null {
  const clean = text.trim().replace(/\s/g, '').replace(',', '.')
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(clean)
  if (!match) return null
  const [, sign, whole = '0', fraction = ''] = match
  const grosze = Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
  return sign ? -grosze : grosze
}

/** 1230 → "12.30", -5 → "-0.05" (the API's decimal format). */
export function fromGrosze(grosze: number): string {
  const sign = grosze < 0 ? '-' : ''
  const abs = Math.abs(grosze)
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`
}
