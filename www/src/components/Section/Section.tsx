import type { ReactNode } from 'react'
import { Container } from '@/components/Container/Container'
import styles from './style.module.css'

interface SectionProps {
  children?: ReactNode
  id?: string
  tone?: 'default' | 'subtle' | 'inverse'
  eyebrow?: string
  title?: string
  intro?: ReactNode
  align?: 'start' | 'center'
  actions?: ReactNode
}

export function Section({ children, id, tone = 'default', eyebrow, title, intro, align = 'start', actions }: SectionProps) {
  const headingId = id && title ? `${id}-title` : undefined

  return (
    <section id={id} className={`${styles.section} ${styles[tone]}`} aria-labelledby={headingId}>
      <Container>
        {title && (
          <header className={`${styles.header} ${styles[align]}`}>
            <div className={styles.heading}>
              {eyebrow && <p className={styles.eyebrow}>{eyebrow}</p>}
              <h2 id={headingId} className={styles.title}>
                {title}
              </h2>
              {intro && <p className={styles.intro}>{intro}</p>}
            </div>
            {actions && <div className={styles.actions}>{actions}</div>}
          </header>
        )}
        {children}
      </Container>
    </section>
  )
}
