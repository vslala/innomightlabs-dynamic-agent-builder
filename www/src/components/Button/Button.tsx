import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Icon, type IconName } from '@/components/Icon/Icon'
import styles from './style.module.css'

type Variant = 'primary' | 'secondary' | 'subtle' | 'inverse' | 'inverse-outline'

interface CommonProps {
  children: ReactNode
  variant?: Variant
  size?: 'md' | 'lg'
  icon?: IconName
}

// One button look for three elements: in-app links, external links and real buttons.
type ButtonProps = CommonProps &
  (
    | { to: string; href?: never }
    | { href: string; to?: never }
    | ({ to?: never; href?: never } & ButtonHTMLAttributes<HTMLButtonElement>)
  )

export function Button({ children, variant = 'primary', size = 'md', icon, ...target }: ButtonProps) {
  const className = `${styles.button} ${styles[variant]} ${styles[size]}`
  const content = (
    <>
      <span>{children}</span>
      {icon && <Icon name={icon} size={18} className={styles.icon} />}
    </>
  )

  if (target.to !== undefined) {
    return (
      <Link to={target.to} className={className}>
        {content}
      </Link>
    )
  }

  if (target.href !== undefined) {
    return (
      <a href={target.href} className={className} target="_blank" rel="noopener">
        {content}
      </a>
    )
  }

  return (
    <button type="button" {...target} className={className}>
      {content}
    </button>
  )
}
