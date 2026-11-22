import { Link, Outlet } from '@tanstack/react-router'

import { ThemeToggle } from '@/components/theme-toggle'

export function Layout() {
  return (
    <div className="min-h-svh bg-background text-foreground">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-4">
          <Link to="/transakcje" className="font-heading text-lg font-semibold">
            🐷 Skarbonka
          </Link>
          <nav className="flex gap-4 text-sm">
            <Link
              to="/transakcje"
              className="text-muted-foreground hover:text-foreground"
              activeProps={{ className: 'text-foreground font-medium' }}
            >
              Transakcje
            </Link>
            <Link
              to="/przeglad"
              className="text-muted-foreground hover:text-foreground"
              activeProps={{ className: 'text-foreground font-medium' }}
            >
              Przegląd
            </Link>
          </nav>
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
