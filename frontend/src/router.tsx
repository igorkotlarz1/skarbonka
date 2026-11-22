// Code-based routes. Filters live in the URL (search params), so a filtered view can be
// bookmarked and survives a page refresh.
import { createRootRoute, createRoute, createRouter, redirect } from '@tanstack/react-router'

import { Layout } from '@/components/layout'
import { parseTransactionSearch } from '@/pages/transaction-search'
import { TransactionsPage } from '@/pages/transactions'

const rootRoute = createRootRoute({ component: Layout })

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    throw redirect({ to: '/transakcje' })
  },
})

export const transactionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/transakcje',
  validateSearch: parseTransactionSearch,
  component: TransactionsPage,
})

export const router = createRouter({
  routeTree: rootRoute.addChildren([indexRoute, transactionsRoute]),
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
