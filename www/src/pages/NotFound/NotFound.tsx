import { Button } from '@/components/Button/Button'
import { Container } from '@/components/Container/Container'
import { LogoMark } from '@/components/Logo/Logo'
import { Seo } from '@/components/Seo/Seo'
import styles from './style.module.css'

export function NotFound() {
  return (
    <>
      <Seo title="Page not found" description="The page you were looking for could not be found." />
      <section className={styles.page}>
        <Container width="narrow" className={styles.inner}>
          <LogoMark size={96} />
          <p className={styles.code}>404</p>
          <h1 className={styles.title}>We couldn't find that page</h1>
          <p className={styles.body}>It may have moved, or the link may be out of date.</p>
          <div className={styles.actions}>
            <Button to="/" icon="arrow-right">
              Go to the home page
            </Button>
            <Button to="/contact" variant="secondary">
              Contact us
            </Button>
          </div>
        </Container>
      </section>
    </>
  )
}
