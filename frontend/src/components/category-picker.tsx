// A keyboard-first category search: type a few letters, ↑/↓ to move, Enter to pick, Esc to leave.
import { forwardRef, useMemo, useState } from 'react'

import type { Category } from '@/api/client'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

const fold = (text: string) =>
  text.normalize('NFD').replace(/\p{Diacritic}/gu, '').replace(/ł/g, 'l').toLowerCase()

type Props = {
  categories: Category[]
  onPick: (path: string) => void
  onCancel?: () => void
}

export const CategoryPicker = forwardRef<HTMLInputElement, Props>(function CategoryPicker(
  { categories, onPick, onCancel },
  ref,
) {
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  // Leaves only: a parent with children is a heading, not a place for a transaction.
  const leaves = useMemo(
    () => categories.filter((c) => c.parent !== null || !categories.some((o) => o.parent === c.name)),
    [categories],
  )
  const matches = useMemo(() => {
    const words = fold(query).split(/\s+/).filter(Boolean)
    return leaves.filter((c) => words.every((w) => fold(c.path).includes(w))).slice(0, 8)
  }, [leaves, query])
  const current = Math.min(active, Math.max(matches.length - 1, 0))

  const pick = (path: string | undefined) => {
    if (!path) return
    onPick(path)
    setQuery('')
    setActive(0)
  }

  return (
    <div className="flex flex-col gap-1">
      <Input
        ref={ref}
        value={query}
        placeholder="Szukaj kategorii…"
        aria-label="Szukaj kategorii"
        onChange={(e) => {
          setQuery(e.target.value)
          setActive(0)
        }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setActive(Math.min(current + 1, matches.length - 1))
          } else if (e.key === 'ArrowUp') {
            e.preventDefault()
            setActive(Math.max(current - 1, 0))
          } else if (e.key === 'Enter') {
            e.preventDefault()
            pick(matches[current]?.path)
          } else if (e.key === 'Escape') {
            setQuery('')
            e.currentTarget.blur()
            onCancel?.()
          }
        }}
      />
      {query && (
        <ul role="listbox" aria-label="Pasujące kategorie" className="rounded-lg border p-1 text-sm">
          {matches.length === 0 && <li className="px-2 py-1 text-muted-foreground">Brak takiej kategorii</li>}
          {matches.map((c, i) => (
            <li
              key={c.path}
              role="option"
              aria-selected={i === current}
              className={cn(
                'cursor-pointer rounded-md px-2 py-1',
                i === current && 'bg-accent text-accent-foreground',
              )}
              onMouseDown={(e) => {
                e.preventDefault() // keep focus in the input until the pick is done
                pick(c.path)
              }}
            >
              {c.parent ? <span className="text-muted-foreground">{c.parent} / </span> : null}
              {c.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
})
