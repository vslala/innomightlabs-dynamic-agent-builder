import { Link } from 'react-router-dom';

import { Footer } from '../../components/Footer';
import { Navbar } from '../../components/Navbar';
import { indexablePages, type SitemapSection } from '../../routes/publicPages';
import styles from './SitemapPage.module.css';

const SECTIONS: SitemapSection[] = ['Product', 'Documentation', 'Legal'];

/** The human-readable sitemap. Search engines read /sitemap.xml, built from the same list. */
export function SitemapPage() {
  const pages = indexablePages();

  return (
    <>
      <Navbar />
      <main className={styles.page}>
        <header className={styles.header}>
          <h1 className={styles.title}>Sitemap</h1>
          <p className={styles.lead}>
            Every public page on InnoMight Labs. Search engines use the{' '}
            <a href="/sitemap.xml">XML sitemap</a>, which lists the same {pages.length} pages.
          </p>
        </header>

        <div className={styles.sections}>
          {SECTIONS.map((section) => {
            const inSection = pages.filter((page) => page.section === section);
            return (
              <section key={section} className={styles.card}>
                <div className={styles.cardHead}>
                  <h2>{section}</h2>
                  <span className={styles.count}>{inSection.length}</span>
                </div>
                <ul className={styles.list}>
                  {inSection.map((page) => (
                    <li key={page.path}>
                      <Link to={page.path} className={styles.link}>
                        <span>{page.title}</span>
                        <code>{page.path}</code>
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      </main>
      <Footer />
    </>
  );
}
