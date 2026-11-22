// TanStack Query hooks: they cache server data and refetch it after every change.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  api,
  type Allocation,
  type AllocationPatch,
  type BulkChange,
  type BulkResult,
  type Category,
  type TransactionPage,
} from './client'

export type TransactionQuery = {
  date_from?: string
  date_to?: string
  category?: string
  merchant?: string
  personal?: boolean
  needs_review?: boolean
  q?: string
  page: number
  page_size: number
}

export function useTransactions(query: TransactionQuery) {
  return useQuery({
    queryKey: ['transactions', query],
    queryFn: () => api.get<TransactionPage>('/transactions', query),
    placeholderData: keepPreviousData, // keep the old page on screen while the next one loads
  })
}

export function useCategories() {
  return useQuery({
    queryKey: ['categories'],
    queryFn: () => api.get<Category[]>('/categories'),
    staleTime: Infinity, // categories change only with `skarbonka seed`
  })
}

export function usePatchAllocation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: AllocationPatch }) =>
      api.patch<Allocation>(`/allocations/${id}`, patch),
    onSuccess: () => client.invalidateQueries({ queryKey: ['transactions'] }),
  })
}

export function useBulkChange() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (change: BulkChange) => api.post<BulkResult>('/allocations/bulk', change),
    onSuccess: () => client.invalidateQueries({ queryKey: ['transactions'] }),
  })
}
