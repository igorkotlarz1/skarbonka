import { MoonIcon, SunIcon } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { applyTheme, initialTheme, type Theme } from '@/lib/theme'

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const next: Theme = theme === 'dark' ? 'light' : 'dark'
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={next === 'dark' ? 'Włącz tryb ciemny' : 'Włącz tryb jasny'}
      onClick={() => {
        applyTheme(next)
        setTheme(next)
      }}
    >
      {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
    </Button>
  )
}
