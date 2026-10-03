import { Icon } from '@/components/Icon/Icon'
import { site } from '@/content/site'
import styles from './style.module.css'

// Certifications and procurement frameworks. Renders nothing until site.credentials has entries.
export function Credentials() {
  if (site.credentials.length === 0) return null

  return (
    <ul className={styles.credentials} aria-label="Certifications and frameworks">
      {site.credentials.map((credential) => (
        <li key={credential} className={styles.credential}>
          <Icon name="shield" size={18} />
          {credential}
        </li>
      ))}
    </ul>
  )
}
