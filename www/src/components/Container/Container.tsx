import type { ReactNode } from 'react'
import styles from './style.module.css'

interface ContainerProps {
  children: ReactNode
  width?: 'default' | 'narrow'
  className?: string
}

export function Container({ children, width = 'default', className }: ContainerProps) {
  return <div className={[styles.container, styles[width], className].filter(Boolean).join(' ')}>{children}</div>
}
