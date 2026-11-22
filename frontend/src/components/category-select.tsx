import { useMemo } from 'react'

import type { Category } from '@/api/client'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

// Radix Select cannot use "" as a value, so "no choice" has its own token.
export const ANY = '__any'

type Group = { parent: Category; children: Category[] }

function groupCategories(categories: Category[]): Group[] {
  const parents = categories.filter((c) => c.parent === null)
  return parents.map((parent) => ({
    parent,
    children: categories.filter((c) => c.parent === parent.name),
  }))
}

type Props = {
  categories: Category[]
  value: string | null
  onChange: (path: string | null) => void
  placeholder: string
  /** Label of the "no category" item; omit to hide it. */
  emptyLabel?: string
  /** In filters a parent can be chosen too, and then it also matches its children. */
  allowParents?: boolean
  size?: 'sm' | 'default'
  className?: string
  disabled?: boolean
}

export function CategorySelect({
  categories,
  value,
  onChange,
  placeholder,
  emptyLabel,
  allowParents = false,
  size = 'default',
  className,
  disabled,
}: Props) {
  const groups = useMemo(() => groupCategories(categories), [categories])
  return (
    <Select
      value={value ?? (emptyLabel ? ANY : '')}
      onValueChange={(v) => onChange(v === ANY ? null : v)}
      disabled={disabled}
    >
      <SelectTrigger size={size} className={className}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent position="popper" className="max-h-80">
        {emptyLabel && (
          <>
            <SelectItem value={ANY}>{emptyLabel}</SelectItem>
            <SelectSeparator />
          </>
        )}
        {groups.map(({ parent, children }) =>
          children.length === 0 ? (
            <SelectItem key={parent.path} value={parent.path}>
              {parent.name}
            </SelectItem>
          ) : (
            <SelectGroup key={parent.path}>
              <SelectLabel>{parent.name}</SelectLabel>
              {allowParents && (
                <SelectItem value={parent.path}>{parent.name} (wszystko)</SelectItem>
              )}
              {children.map((child) => (
                <SelectItem key={child.path} value={child.path}>
                  {child.name}
                </SelectItem>
              ))}
            </SelectGroup>
          ),
        )}
      </SelectContent>
    </Select>
  )
}
