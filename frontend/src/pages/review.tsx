// The review queue: one uncategorized transaction at a time, driven from the keyboard.
import { CheckIcon, ChevronLeftIcon, ChevronRightIcon, ScissorsIcon } from 'lucide-react'
import { type ReactNode, useEffect, useLayoutEffect, useRef, useState } from 'react'

import type { RuleSuggestion } from '@/api/client'
import {
  useAcceptSuggestion,
  useCategories,
  useCreateRule,
  usePatchAllocation,
  useTransactions,
} from '@/api/hooks'
import { CategoryPicker } from '@/components/category-picker'
import { SplitDialog } from '@/components/split-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Switch } from '@/components/ui/switch'
import { formatAmount, formatConfidence, formatDate, isNegative } from '@/lib/format'
import { cn } from '@/lib/utils'

const QUEUE_SIZE = 200

/** Shortcuts must not fire while the owner types into a field or a dialog is open. */
function typingInto(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return (
    target.isContentEditable ||
    ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) ||
    target.closest('[role="dialog"], [role="listbox"]') !== null
  )
}

export function ReviewPage() {
  const queue = useTransactions({ needs_review: true, page: 1, page_size: QUEUE_SIZE })
  const categories = useCategories().data ?? []
  const patch = usePatchAllocation()
  const accept = useAcceptSuggestion()
  const createRule = useCreateRule()

  const [index, setIndex] = useState(0)
  const [remember, setRemember] = useState(false)
  const [splitting, setSplitting] = useState(false)
  const [suggestion, setSuggestion] = useState<RuleSuggestion | null>(null)
  const [ruleSaved, setRuleSaved] = useState<string | null>(null)
  const picker = useRef<HTMLInputElement>(null)

  const items = queue.data?.items ?? []
  const position = Math.min(index, Math.max(items.length - 1, 0))
  const current = items[position]
  // In a split, review the first part still without a category.
  const allocation =
    current?.allocations.find((a) => a.category === null) ?? current?.allocations[0]
  const partNumber = current && allocation ? current.allocations.indexOf(allocation) + 1 : 0
  const busy = patch.isPending || accept.isPending
  const error = queue.error ?? patch.error ?? accept.error ?? createRule.error

  // Categorized rows leave the queue on refetch, so the same position shows the next one.
  const choose = (category: string) => {
    picker.current?.blur() // hand the keyboard back to the shortcuts
    if (!allocation) return
    patch.mutate(
      { id: allocation.id, patch: { category } },
      { onSuccess: (result) => setSuggestion(result.rule_suggestion ?? null) },
    )
  }
  const acceptSuggestion = () => {
    if (!allocation?.suggested_category || busy) return
    accept.mutate({ id: allocation.id, remember })
  }
  const togglePersonal = () => {
    if (!allocation || busy) return
    patch.mutate({ id: allocation.id, patch: { personal: !allocation.personal } })
  }
  const saveRule = () => {
    if (!suggestion) return
    createRule.mutate(suggestion.rule, {
      onSuccess: () => {
        setRuleSaved(suggestion.rule.name)
        setSuggestion(null)
      },
    })
  }

  // The handler reads the latest state through a ref, so the listener is added only once.
  const keys = useRef<(e: KeyboardEvent) => void>(() => {})
  const handleKey = (e: KeyboardEvent) => {
    if (e.ctrlKey || e.metaKey || e.altKey || splitting || typingInto(e.target)) return
    // Enter on a focused button already clicks it; do not accept the suggestion on top.
    if (e.key === 'Enter' && e.target instanceof HTMLElement && e.target.closest('button, a')) return
    const actions: Record<string, () => void> = {
      Enter: acceptSuggestion,
      '/': () => picker.current?.focus(),
      o: togglePersonal,
      p: () => current && setSplitting(true),
      z: () => setRemember((r) => !r),
      r: saveRule,
      ArrowRight: () => setIndex(Math.min(position + 1, items.length - 1)),
      ArrowLeft: () => setIndex(Math.max(position - 1, 0)),
    }
    const action = actions[e.key.length === 1 ? e.key.toLowerCase() : e.key]
    if (action) {
      e.preventDefault()
      action()
    }
  }
  useLayoutEffect(() => {
    keys.current = handleKey
  })
  useEffect(() => {
    const listener = (e: KeyboardEvent) => keys.current(e)
    window.addEventListener('keydown', listener)
    return () => window.removeEventListener('keydown', listener)
  }, [])

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="font-heading text-2xl font-semibold">Przegląd</h1>
        {queue.data && (
          <span className="text-sm text-muted-foreground">
            {queue.data.total === 0
              ? 'Kolejka pusta'
              : `${position + 1} z ${queue.data.total} do przejrzenia`}
          </span>
        )}
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm"
        >
          Coś poszło nie tak: {error.message}
        </div>
      )}

      {suggestion && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted px-3 py-2 text-sm">
          <span>
            Zrobić z tego regułę <strong>{suggestion.rule.name}</strong>?
            {suggestion.would_change > 0 &&
              ` Zmieni też ${suggestion.would_change} innych transakcji.`}
          </span>
          <div className="ml-auto flex gap-2">
            <Button size="sm" onClick={saveRule} disabled={createRule.isPending}>
              Tak, dodaj regułę <Kbd>R</Kbd>
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setSuggestion(null)}>
              Nie teraz
            </Button>
          </div>
        </div>
      )}
      {ruleSaved && !suggestion && (
        <p className="text-sm text-muted-foreground">Dodano regułę „{ruleSaved}”.</p>
      )}

      {queue.isPending && <p className="text-muted-foreground">Wczytuję…</p>}
      {queue.data && !current && (
        <div className="rounded-lg border px-6 py-12 text-center">
          <p className="text-lg font-medium">Wszystko przejrzane 🎉</p>
          <p className="text-sm text-muted-foreground">
            Nowe transakcje bez kategorii pojawią się tu po imporcie.
          </p>
        </div>
      )}

      {current && allocation && (
        <div
          className={cn(
            'flex flex-col gap-5 rounded-xl border p-6',
            (queue.isFetching || busy) && 'opacity-70',
          )}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-sm text-muted-foreground">
                {formatDate(current.transaction_date)} · {current.account}
              </p>
              <p className="truncate text-xl font-semibold">
                {current.merchant ?? (current.counterparty || current.title)}
              </p>
              {current.merchant && current.counterparty && (
                <p className="truncate text-sm text-muted-foreground">{current.counterparty}</p>
              )}
              {(current.merchant || current.counterparty) && (
                <p className="truncate text-sm text-muted-foreground">{current.title}</p>
              )}
            </div>
            <p
              className={cn(
                'text-2xl font-semibold tabular-nums whitespace-nowrap',
                !isNegative(current.amount) && 'text-emerald-600 dark:text-emerald-400',
              )}
            >
              {formatAmount(current.amount, current.currency)}
            </p>
          </div>

          {current.allocations.length > 1 && (
            <Badge variant="secondary" className="w-fit">
              Część {partNumber} z {current.allocations.length}:{' '}
              {formatAmount(allocation.amount, current.currency)}
            </Badge>
          )}

          {allocation.suggested_category ? (
            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={acceptSuggestion} disabled={busy}>
                <CheckIcon /> {allocation.suggested_category}
                {allocation.confidence && ` (${formatConfidence(allocation.confidence)})`}
                <Kbd>Enter</Kbd>
              </Button>
              <label className="flex items-center gap-1.5 text-sm">
                <Checkbox
                  checked={remember}
                  onCheckedChange={(on) => setRemember(on === true)}
                  disabled={!current.merchant}
                />
                zapamiętaj dla sprzedawcy <Kbd>Z</Kbd>
              </label>
            </div>
          ) : (
            <Badge variant="outline" className="w-fit">
              Model nie ma podpowiedzi
            </Badge>
          )}

          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">
              Inna kategoria <Kbd>/</Kbd>
            </span>
            <CategoryPicker ref={picker} categories={categories} onPick={choose} />
          </div>

          <div className="flex flex-wrap items-center gap-4 border-t pt-4">
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={allocation.personal} onCheckedChange={togglePersonal} />
              osobiste <Kbd>O</Kbd>
            </label>
            <Button variant="outline" size="sm" onClick={() => setSplitting(true)}>
              <ScissorsIcon /> Podziel <Kbd>P</Kbd>
            </Button>
            <div className="ml-auto flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                disabled={position === 0}
                onClick={() => setIndex(position - 1)}
              >
                <ChevronLeftIcon /> Poprzednia <Kbd>←</Kbd>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={position >= items.length - 1}
                onClick={() => setIndex(position + 1)}
              >
                Pomiń <Kbd>→</Kbd> <ChevronRightIcon />
              </Button>
            </div>
          </div>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Skróty działają, gdy kursor nie stoi w polu tekstowym. Esc wychodzi z wyszukiwania kategorii.
      </p>

      <SplitDialog
        transaction={splitting && current ? current : null}
        categories={categories}
        onClose={() => setSplitting(false)}
      />
    </div>
  )
}

function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="ml-1 rounded border bg-background px-1 font-mono text-[0.7rem] text-muted-foreground">
      {children}
    </kbd>
  )
}
