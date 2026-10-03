import type { Accent } from '@/content/site'
import { Icon, type IconName } from '@/components/Icon/Icon'
import styles from './style.module.css'

interface AccentTileProps {
  icon: IconName
  accent: Accent
  size?: 'sm' | 'md'
}

// The coloured icon tile that identifies a product or service.
export function AccentTile({ icon, accent, size = 'md' }: AccentTileProps) {
  return (
    <span className={`${styles.tile} ${styles[accent]} ${styles[size]}`}>
      <Icon name={icon} size={size === 'sm' ? 18 : 22} />
    </span>
  )
}
