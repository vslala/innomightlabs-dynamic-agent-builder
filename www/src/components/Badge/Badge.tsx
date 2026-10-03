import type { ReactNode } from 'react'
import styles from './style.module.css'

interface BadgeProps {
  children: ReactNode
  tone?: 'neutral' | 'success' | 'discovery' | 'warning'
}

export function Badge({ children, tone = 'neutral' }: BadgeProps) {
  return <span className={`${styles.badge} ${styles[tone]}`}>{children}</span>
}
