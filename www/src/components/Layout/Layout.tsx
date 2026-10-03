import { Outlet, ScrollRestoration } from 'react-router-dom'
import { Footer } from '@/components/Footer/Footer'
import { Header } from '@/components/Header/Header'
import { useScrollToHash } from '@/hooks/useScrollToHash'
import styles from './style.module.css'

export function Layout() {
  useScrollToHash()

  return (
    <div className={styles.layout}>
      <a href="#main" className={styles.skipLink}>
        Skip to content
      </a>
      <Header />
      <main id="main" className={styles.main} tabIndex={-1}>
        <Outlet />
      </main>
      <Footer />
      <ScrollRestoration />
    </div>
  )
}
