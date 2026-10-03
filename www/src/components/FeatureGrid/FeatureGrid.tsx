import { Icon, type IconName } from '@/components/Icon/Icon'
import styles from './style.module.css'

export interface Feature {
  title: string
  body: string
  icon?: IconName
}

interface FeatureGridProps {
  features: Feature[]
  columns?: 2 | 3 | 4
  tone?: 'default' | 'inverse'
}

export function FeatureGrid({ features, columns = 3, tone = 'default' }: FeatureGridProps) {
  return (
    <ul className={`${styles.grid} ${styles[`columns${columns}`]} ${styles[tone]}`}>
      {features.map((feature) => (
        <li key={feature.title} className={styles.feature}>
          <span className={styles.icon}>
            <Icon name={feature.icon ?? 'check'} size={20} />
          </span>
          <h3 className={styles.title}>{feature.title}</h3>
          <p className={styles.body}>{feature.body}</p>
        </li>
      ))}
    </ul>
  )
}
