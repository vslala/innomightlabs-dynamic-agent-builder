import type { ReactNode } from 'react'
import { Container } from '@/components/Container/Container'
import styles from './style.module.css'

interface PageHeroProps {
  eyebrow: string
  title: string
  intro: ReactNode
  actions?: ReactNode
  aside?: ReactNode
}

// The opening band of every inner page.
export function PageHero({ eyebrow, title, intro, actions, aside }: PageHeroProps) {
  return (
    <section className={styles.hero}>
      <Container className={`${styles.inner} ${aside ? styles.withAside : ''}`}>
        <div className={styles.text}>
          <p className={styles.eyebrow}>{eyebrow}</p>
          <h1 className={styles.title}>{title}</h1>
          <p className={styles.intro}>{intro}</p>
          {actions && <div className={styles.actions}>{actions}</div>}
        </div>
        {aside && <div className={styles.aside}>{aside}</div>}
      </Container>
    </section>
  )
}
