import { Button } from '@/components/Button/Button'
import { Container } from '@/components/Container/Container'
import { site } from '@/content/site'
import styles from './style.module.css'

interface CtaBannerProps {
  title?: string
  body?: string
}

export function CtaBanner({
  title = 'Have a project or tender in mind?',
  body = 'Tell us what you are trying to achieve. We will reply within two working days with honest advice on how we can help, even if that means pointing you elsewhere.',
}: CtaBannerProps) {
  return (
    <section className={styles.banner} aria-labelledby="cta-title">
      <Container className={styles.inner}>
        <div className={styles.text}>
          <h2 id="cta-title" className={styles.title}>
            {title}
          </h2>
          <p className={styles.body}>{body}</p>
        </div>
        <div className={styles.actions}>
          <Button to="/contact" variant="inverse" size="lg" icon="arrow-right">
            Start a conversation
          </Button>
          <a className={styles.email} href={`mailto:${site.email}`}>
            or email {site.email}
          </a>
        </div>
      </Container>
    </section>
  )
}
