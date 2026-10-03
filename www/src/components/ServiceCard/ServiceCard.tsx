import { Link } from 'react-router-dom'
import { AccentTile } from '@/components/AccentTile/AccentTile'
import { Icon } from '@/components/Icon/Icon'
import type { Service } from '@/content/services'
import styles from './style.module.css'

export function ServiceCard({ service }: { service: Service }) {
  return (
    <Link to={`/services#${service.id}`} className={`${styles.card} ${styles[service.accent]}`}>
      <AccentTile icon={service.icon} accent={service.accent} />
      <h3 className={styles.title}>{service.title}</h3>
      <p className={styles.summary}>{service.summary}</p>
      <span className={styles.more}>
        Learn more <Icon name="arrow-right" size={16} />
      </span>
    </Link>
  )
}
