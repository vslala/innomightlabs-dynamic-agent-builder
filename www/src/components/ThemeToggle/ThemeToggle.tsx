import { useTheme } from '@/hooks/useTheme'
import { Icon } from '@/components/Icon/Icon'
import styles from './style.module.css'

export function ThemeToggle() {
  const { theme, cycleTheme } = useTheme()
  const label = theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'

  // Both icons are rendered and CSS picks one from the page's data-theme, so the right icon shows on
  // first paint even before React has hydrated.
  return (
    <button type="button" className={styles.toggle} onClick={cycleTheme} aria-label={label} title={label}>
      <Icon name="moon" className={styles.moon} />
      <Icon name="sun" className={styles.sun} />
    </button>
  )
}
