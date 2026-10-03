import type { ReactNode } from 'react'
import styles from './style.module.css'

// Long-form text such as policies and articles: comfortable measure and spacing for reading.
export function Prose({ children }: { children: ReactNode }) {
  return <div className={styles.prose}>{children}</div>
}
