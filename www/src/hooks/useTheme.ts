import { useCallback, useEffect, useState } from 'react'

// Every theme in src/styles/tokens.css, in the order the toggle cycles through them.
export const themes = ['light', 'dark'] as const
export type Theme = (typeof themes)[number]

const STORAGE_KEY = 'theme'

function currentTheme(): Theme {
  const applied = document.documentElement.dataset.theme
  return themes.find((theme) => theme === applied) ?? 'light'
}

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
}

// index.html applies the saved or system theme before first paint. This hook takes over from there:
// it switches themes and keeps following the system until the visitor makes their own choice.
export function useTheme() {
  // Prerendered HTML has no theme, so start from the default and sync once mounted.
  const [theme, setTheme] = useState<Theme>('light')

  useEffect(() => {
    setTheme(currentTheme())

    const system = window.matchMedia('(prefers-color-scheme: dark)')
    const followSystem = (event: MediaQueryListEvent) => {
      if (localStorage.getItem(STORAGE_KEY)) return
      const next: Theme = event.matches ? 'dark' : 'light'
      applyTheme(next)
      setTheme(next)
    }
    system.addEventListener('change', followSystem)
    return () => system.removeEventListener('change', followSystem)
  }, [])

  const cycleTheme = useCallback(() => {
    const next = themes[(themes.indexOf(currentTheme()) + 1) % themes.length]
    applyTheme(next)
    localStorage.setItem(STORAGE_KEY, next)
    setTheme(next)
  }, [])

  return { theme, cycleTheme }
}
