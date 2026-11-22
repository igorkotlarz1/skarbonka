import { useNavigate, useSearch } from '@tanstack/react-router'
import { ChevronLeftIcon, ChevronRightIcon, ScissorsIcon, XIcon } from 'lucide-react'
import { type ReactNode, useEffect, useState } from 'react'

import type { Allocation, Category, Transaction } from '@/api/client'
import {
  useBulkChange,
  useCategories,
  usePatchAllocation,
  useTransactions,
} from '@/api/hooks'
import { ANY, CategorySelect } from '@/components/category-select'
import { SplitDialog } from '@/components/split-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatAmount, formatConfidence, formatDate, isNegative } from '@/lib/format'
import { cn } from '@/lib/utils'
import { toQuery, type TransactionSearch } from '@/pages/transaction-search'

// ---------------------------------------------------------------- page

export function TransactionsPage() {
  const search = useSearch({ from: '/transakcje' })
  const navigate = useNavigate({ from: '/transakcje' })
  // A filter change always goes back to page 1.
  const setFilters = (patch: Partial<TransactionSearch>) =>
    void navigate({ search: (prev) => ({ ...prev, ...patch, page: undefined }) })
  const setPage = (page: number) =>
    void navigate({ search: (prev) => ({ ...prev, page: page > 1 ? page : undefined }) })

  const transactions = useTransactions(toQuery(search))
  const categories = useCategories().data ?? []
  const patch = usePatchAllocation()
  const bulk = useBulkChange()
  const [splitting, setSplitting] = useState<Transaction | null>(null)

  // Selection belongs to one view: changing filters or the page clears it.
  const viewKey = JSON.stringify(search)
  const [selection, setSelection] = useState<{ view: string; ids: Set<number> }>({
    view: viewKey,
    ids: new Set(),
  })
  const selected = selection.view === viewKey ? selection.ids : new Set<number>()
  const setSelected = (ids: Set<number>) => setSelection({ view: viewKey, ids })

  const page = transactions.data
  const rows = page?.items ?? []
  const pageIds = rows.flatMap((t) => t.allocations.map((a) => a.id))
  const allSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id))
  const someSelected = pageIds.some((id) => selected.has(id))
  const pages = page ? Math.max(1, Math.ceil(page.total / page.page_size)) : 1
  const error = transactions.error ?? patch.error ?? bulk.error

  const toggle = (ids: number[], on: boolean) => {
    const next = new Set(selected)
    for (const id of ids) {
      if (on) next.add(id)
      else next.delete(id)
    }
    setSelected(next)
  }

  const applyBulk = (change: { category?: string | null; personal?: boolean }) =>
    bulk.mutate(
      { allocation_ids: [...selected], ...change },
      { onSuccess: () => setSelected(new Set()) },
    )

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between gap-4">
        <h1 className="font-heading text-2xl font-semibold">Transakcje</h1>
        {page && (
          <span className="text-sm text-muted-foreground">
            {page.total} {plural(page.total, 'transakcja', 'transakcje', 'transakcji')}
          </span>
        )}
      </div>

      <Filters search={search} categories={categories} onChange={setFilters} />

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm"
        >
          Coś poszło nie tak: {error.message}
        </div>
      )}

      {selected.size > 0 && (
        <BulkBar
          count={selected.size}
          categories={categories}
          busy={bulk.isPending}
          onCategory={(category) => applyBulk({ category })}
          onPersonal={(personal) => applyBulk({ personal })}
          onClear={() => setSelected(new Set())}
        />
      )}

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <Checkbox
                  aria-label="Zaznacz całą stronę"
                  checked={allSelected ? true : someSelected ? 'indeterminate' : false}
                  onCheckedChange={(on) => toggle(pageIds, on === true)}
                />
              </TableHead>
              <TableHead className="w-28">Data</TableHead>
              <TableHead>Sprzedawca / tytuł</TableHead>
              <TableHead className="w-36 text-right">Kwota</TableHead>
              <TableHead className="w-80">Kategoria</TableHead>
              <TableHead className="w-24 text-center">Osobiste</TableHead>
              <TableHead className="w-12">
                <span className="sr-only">Podziel</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody className={cn(transactions.isPlaceholderData && 'opacity-60')}>
            {rows.map((t) => (
              <TransactionRow
                key={t.id}
                transaction={t}
                categories={categories}
                selected={selected}
                onSelect={toggle}
                onMerchant={(merchant) => setFilters({ merchant })}
                onPatch={(id, change) => patch.mutate({ id, patch: change })}
                onSplit={() => setSplitting(t)}
              />
            ))}
            {page && rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  Brak transakcji dla tych filtrów.
                </TableCell>
              </TableRow>
            )}
            {transactions.isPending && (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-muted-foreground">
                  Wczytuję…
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {page && pages > 1 && (
        <div className="flex items-center justify-end gap-2 text-sm">
          <Button
            variant="outline"
            size="sm"
            disabled={page.page <= 1}
            onClick={() => setPage(page.page - 1)}
          >
            <ChevronLeftIcon /> Poprzednia
          </Button>
          <span className="text-muted-foreground">
            Strona {page.page} z {pages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page.page >= pages}
            onClick={() => setPage(page.page + 1)}
          >
            Następna <ChevronRightIcon />
          </Button>
        </div>
      )}
      <SplitDialog
        transaction={splitting}
        categories={categories}
        onClose={() => setSplitting(null)}
      />
    </div>
  )
}

// ---------------------------------------------------------------- filters

type FiltersProps = {
  search: TransactionSearch
  categories: Category[]
  onChange: (patch: Partial<TransactionSearch>) => void
}

function Filters({ search, categories, onChange }: FiltersProps) {
  // The text box waits for a pause in typing before it filters.
  const [q, setQ] = useState(search.q ?? '')
  useEffect(() => {
    const timer = setTimeout(() => {
      const value = q.trim() || undefined
      if (value !== search.q) onChange({ q: value })
    }, 300)
    return () => clearTimeout(timer)
  }, [q, search.q, onChange])

  const active = Object.entries(search).some(([key, value]) => key !== 'page' && value !== undefined)

  return (
    <div className="flex flex-wrap items-end gap-3">
      <Field label="Szukaj">
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="kontrahent lub tytuł"
          className="w-56"
        />
      </Field>
      <Field label="Od">
        <Input
          type="date"
          value={search.from ?? ''}
          onChange={(e) => onChange({ from: e.target.value || undefined })}
          className="w-40"
        />
      </Field>
      <Field label="Do">
        <Input
          type="date"
          value={search.to ?? ''}
          onChange={(e) => onChange({ to: e.target.value || undefined })}
          className="w-40"
        />
      </Field>
      <Field label="Kategoria">
        <CategorySelect
          categories={categories}
          value={search.category ?? null}
          onChange={(category) => onChange({ category: category ?? undefined })}
          placeholder="Wszystkie"
          emptyLabel="Wszystkie"
          allowParents
          className="w-56"
        />
      </Field>
      <Field label="Osobiste">
        <TriState
          value={search.personal}
          onChange={(personal) => onChange({ personal })}
          labels={['Wszystkie', 'Tylko osobiste', 'Bez osobistych']}
        />
      </Field>
      <Field label="Przegląd">
        <TriState
          value={search.review}
          onChange={(review) => onChange({ review })}
          labels={['Wszystkie', 'Do przeglądu', 'Skategoryzowane']}
        />
      </Field>
      {search.merchant && (
        <Badge variant="secondary" className="h-8 gap-1 px-3">
          Sprzedawca: {search.merchant}
          <button
            type="button"
            aria-label="Usuń filtr sprzedawcy"
            onClick={() => onChange({ merchant: undefined })}
          >
            <XIcon className="size-3.5" />
          </button>
        </Badge>
      )}
      {active && (
        <Button
          variant="ghost"
          onClick={() => {
            setQ('')
            onChange({
              from: undefined,
              to: undefined,
              category: undefined,
              merchant: undefined,
              personal: undefined,
              review: undefined,
              q: undefined,
            })
          }}
        >
          Wyczyść filtry
        </Button>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-muted-foreground">
      {label}
      {children}
    </label>
  )
}

function TriState({
  value,
  onChange,
  labels,
}: {
  value: boolean | undefined
  onChange: (value: boolean | undefined) => void
  labels: [string, string, string]
}) {
  const current = value === undefined ? ANY : value ? 'yes' : 'no'
  return (
    <Select
      value={current}
      onValueChange={(v) => onChange(v === ANY ? undefined : v === 'yes')}
    >
      <SelectTrigger className="w-40">
        <SelectValue />
      </SelectTrigger>
      <SelectContent position="popper">
        <SelectItem value={ANY}>{labels[0]}</SelectItem>
        <SelectItem value="yes">{labels[1]}</SelectItem>
        <SelectItem value="no">{labels[2]}</SelectItem>
      </SelectContent>
    </Select>
  )
}

// ---------------------------------------------------------------- bulk actions

type BulkBarProps = {
  count: number
  categories: Category[]
  busy: boolean
  onCategory: (category: string) => void
  onPersonal: (personal: boolean) => void
  onClear: () => void
}

function BulkBar({ count, categories, busy, onCategory, onPersonal, onClear }: BulkBarProps) {
  const [category, setCategory] = useState<string | null>(null)
  return (
    <div className="sticky top-2 z-10 flex flex-wrap items-center gap-2 rounded-lg border bg-muted px-3 py-2 text-sm shadow-sm">
      <span className="font-medium">
        Zaznaczono: {count}
      </span>
      <CategorySelect
        categories={categories}
        value={category}
        onChange={setCategory}
        placeholder="Wybierz kategorię"
        size="sm"
        className="w-56 bg-background"
      />
      <Button size="sm" disabled={!category || busy} onClick={() => category && onCategory(category)}>
        Zmień kategorię
      </Button>
      <Button size="sm" variant="outline" disabled={busy} onClick={() => onPersonal(true)}>
        Oznacz jako osobiste
      </Button>
      <Button size="sm" variant="outline" disabled={busy} onClick={() => onPersonal(false)}>
        Nie osobiste
      </Button>
      <Button size="sm" variant="ghost" className="ml-auto" onClick={onClear}>
        Odznacz
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------- one row

type RowProps = {
  transaction: Transaction
  categories: Category[]
  selected: Set<number>
  onSelect: (ids: number[], on: boolean) => void
  onMerchant: (merchant: string) => void
  onPatch: (allocationId: number, change: { category?: string | null; personal?: boolean }) => void
  onSplit: () => void
}

function TransactionRow({
  transaction: t,
  categories,
  selected,
  onSelect,
  onMerchant,
  onPatch,
  onSplit,
}: RowProps) {
  const ids = t.allocations.map((a) => a.id)
  // Splits (several allocations) get their own editor later; the list edits the first part.
  const allocation = t.allocations[0]
  const isSelected = ids.length > 0 && ids.every((id) => selected.has(id))
  return (
    <TableRow data-state={isSelected ? 'selected' : undefined}>
      <TableCell>
        <Checkbox
          aria-label="Zaznacz transakcję"
          checked={isSelected}
          onCheckedChange={(on) => onSelect(ids, on === true)}
        />
      </TableCell>
      <TableCell className="tabular-nums">{formatDate(t.transaction_date)}</TableCell>
      <TableCell className="max-w-0">
        <div className="flex flex-col">
          {t.merchant ? (
            <button
              type="button"
              className="w-fit font-medium hover:underline"
              title="Pokaż tylko tego sprzedawcę"
              onClick={() => t.merchant && onMerchant(t.merchant)}
            >
              {t.merchant}
            </button>
          ) : (
            <span className="truncate font-medium">{t.counterparty || '—'}</span>
          )}
          <span className="truncate text-xs text-muted-foreground" title={t.title}>
            {t.merchant ? t.counterparty : t.title}
          </span>
        </div>
      </TableCell>
      <TableCell
        className={cn(
          'text-right font-medium tabular-nums',
          isNegative(t.amount) ? 'text-foreground' : 'text-emerald-600 dark:text-emerald-400',
        )}
      >
        {formatAmount(t.amount, t.currency)}
      </TableCell>
      <TableCell>
        {allocation && (
          <CategoryCell
            allocation={allocation}
            parts={t.allocations.length}
            categories={categories}
            onPatch={(change) => onPatch(allocation.id, change)}
          />
        )}
      </TableCell>
      <TableCell className="text-center">
        {allocation && (
          <Switch
            aria-label="Wydatek osobisty"
            checked={allocation.personal}
            onCheckedChange={(personal) => onPatch(allocation.id, { personal })}
          />
        )}
      </TableCell>
      <TableCell>
        <Button variant="ghost" size="icon-sm" aria-label="Podziel transakcję" onClick={onSplit}>
          <ScissorsIcon />
        </Button>
      </TableCell>
    </TableRow>
  )
}

const SOURCE_LABEL: Record<string, string> = {
  manual: 'ręcznie',
  rule: 'reguła',
  merchant: 'sprzedawca',
  import: 'import',
  llm: 'LLM',
}

function CategoryCell({
  allocation: a,
  parts,
  categories,
  onPatch,
}: {
  allocation: Allocation
  parts: number
  categories: Category[]
  onPatch: (change: { category?: string | null }) => void
}) {
  const source =
    a.source === 'ml' && a.confidence ? `model ${formatConfidence(a.confidence)}` : SOURCE_LABEL[a.source]
  return (
    <div className="flex flex-col gap-1">
      <CategorySelect
        categories={categories}
        value={a.category}
        onChange={(category) => onPatch({ category })}
        placeholder="Bez kategorii"
        size="sm"
        className="w-full"
      />
      <div className="flex flex-wrap items-center gap-1">
        {a.category === null && a.suggested_category ? (
          <Button
            size="xs"
            variant="outline"
            title="Przyjmij podpowiedź modelu"
            onClick={() => onPatch({ category: a.suggested_category })}
          >
            ✓ {a.suggested_category.split('/').pop()}
            {a.confidence && ` (${formatConfidence(a.confidence)})`}
          </Button>
        ) : a.category === null ? (
          <Badge variant="outline">do przeglądu</Badge>
        ) : (
          <Badge variant="ghost" className="px-0 text-muted-foreground">
            {source}
          </Badge>
        )}
        {parts > 1 && <Badge variant="secondary">podział na {parts}</Badge>}
      </div>
    </div>
  )
}

function plural(n: number, one: string, few: string, many: string): string {
  if (n === 1) return one
  const tens = n % 100
  const units = n % 10
  return units >= 2 && units <= 4 && (tens < 12 || tens > 14) ? few : many
}
