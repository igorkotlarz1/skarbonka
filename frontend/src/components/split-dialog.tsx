// Split one bank transaction into parts (a receipt with groceries and something personal).
// Amounts are typed without a sign; the transaction's sign is applied to every part.
import { PlusIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import type { Category, Transaction } from '@/api/client'
import { useSplit } from '@/api/hooks'
import { CategorySelect } from '@/components/category-select'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { formatAmount } from '@/lib/format'
import { fromGrosze, toGrosze } from '@/lib/money'

type Part = { amount: string; category: string | null; personal: boolean }

/** "-12.30" → "12,30" for the input box. */
const unsigned = (amount: string) => amount.replace(/^[-+]/, '').replace('.', ',')

function startingParts(t: Transaction): Part[] {
  return t.allocations.map((a) => ({
    amount: unsigned(a.amount),
    category: a.category,
    personal: a.personal,
  }))
}

type Props = {
  transaction: Transaction | null
  categories: Category[]
  onClose: () => void
}

export function SplitDialog({ transaction, categories, onClose }: Props) {
  return (
    <Dialog open={transaction !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        {transaction && (
          // Keyed so every opened transaction starts from its own parts.
          <SplitForm
            key={transaction.id}
            transaction={transaction}
            categories={categories}
            onDone={onClose}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function SplitForm({
  transaction: t,
  categories,
  onDone,
}: {
  transaction: Transaction
  categories: Category[]
  onDone: () => void
}) {
  const [parts, setParts] = useState<Part[]>(() => startingParts(t))
  const split = useSplit()

  const sign = t.amount.trim().startsWith('-') ? -1 : 1
  const total = Math.abs(toGrosze(t.amount) ?? 0)
  const typed = parts.map((p) => toGrosze(p.amount))
  const invalid = typed.some((g) => g === null || g <= 0)
  const used = typed.reduce<number>((sum, g) => sum + (g ?? 0), 0)
  const left = total - used
  const canSave = !invalid && left === 0 && !split.isPending

  const update = (index: number, change: Partial<Part>) =>
    setParts(parts.map((p, i) => (i === index ? { ...p, ...change } : p)))

  const save = () =>
    split.mutate(
      {
        id: t.id,
        split: {
          parts: parts.map((p) => ({
            amount: fromGrosze(sign * (toGrosze(p.amount) ?? 0)),
            category: p.category,
            personal: p.personal,
          })),
        },
      },
      { onSuccess: onDone },
    )

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (canSave) save()
      }}
    >
      <DialogHeader>
        <DialogTitle>Podziel transakcję</DialogTitle>
        <DialogDescription>
          {t.merchant ?? (t.counterparty || t.title)} · {formatAmount(t.amount, t.currency)}. Części muszą
          dać razem dokładnie tę kwotę.
        </DialogDescription>
      </DialogHeader>

      <div className="flex flex-col gap-2">
        {parts.map((part, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <Input
              aria-label={`Kwota części ${i + 1}`}
              inputMode="decimal"
              value={part.amount}
              onChange={(e) => update(i, { amount: e.target.value })}
              aria-invalid={typed[i] === null || (typed[i] ?? 0) <= 0}
              className="w-28 text-right tabular-nums"
              autoFocus={i === parts.length - 1 && parts.length > 1}
            />
            <CategorySelect
              categories={categories}
              value={part.category}
              onChange={(category) => update(i, { category })}
              placeholder="Bez kategorii"
              className="w-60"
            />
            <label className="flex items-center gap-1.5 text-sm">
              <Checkbox
                checked={part.personal}
                onCheckedChange={(on) => update(i, { personal: on === true })}
              />
              osobiste
            </label>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              title="Wpisz tu resztę"
              disabled={left === 0}
              onClick={() => update(i, { amount: unsigned(fromGrosze((typed[i] ?? 0) + left)) })}
            >
              + reszta
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Usuń część ${i + 1}`}
              disabled={parts.length === 1}
              onClick={() => setParts(parts.filter((_, j) => j !== i))}
            >
              <Trash2Icon />
            </Button>
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="w-fit"
          onClick={() =>
            setParts([
              ...parts,
              { amount: left > 0 ? unsigned(fromGrosze(left)) : '', category: null, personal: false },
            ])
          }
        >
          <PlusIcon /> Dodaj część
        </Button>
      </div>

      <p
        className={left === 0 ? 'text-sm text-muted-foreground' : 'text-sm font-medium text-destructive'}
        aria-live="polite"
      >
        {invalid
          ? 'Każda część potrzebuje kwoty większej od zera.'
          : left === 0
            ? 'Wszystko rozdzielone.'
            : left > 0
              ? `Zostało do rozdzielenia: ${formatAmount(fromGrosze(left), t.currency)}`
              : `Za dużo o ${formatAmount(fromGrosze(-left), t.currency)}`}
      </p>
      {split.error && (
        <p role="alert" className="text-sm text-destructive">
          Nie zapisano: {split.error.message}
        </p>
      )}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone}>
          Anuluj
        </Button>
        <Button type="submit" disabled={!canSave}>
          {parts.length === 1 ? 'Zapisz bez podziału' : `Zapisz ${parts.length} części`}
        </Button>
      </DialogFooter>
    </form>
  )
}
