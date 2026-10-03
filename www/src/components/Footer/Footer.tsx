import { Link } from 'react-router-dom'
import { Container } from '@/components/Container/Container'
import { Logo } from '@/components/Logo/Logo'
import { productPath, products } from '@/content/products'
import { services } from '@/content/services'
import { site } from '@/content/site'
import styles from './style.module.css'

const columns = [
  {
    title: 'Software',
    links: [...products.map((product) => ({ label: product.name, to: productPath(product) })), { label: 'All software', to: '/software' }],
  },
  {
    title: 'Services',
    links: services.map((service) => ({ label: service.title, to: `/services#${service.id}` })),
  },
  {
    title: 'Company',
    links: [
      { label: 'About us', to: '/about' },
      { label: 'Public sector', to: '/public-sector' },
      { label: 'Insights', to: '/insights' },
      { label: 'Contact', to: '/contact' },
    ],
  },
]

export function Footer() {
  const disclosures = [
    site.companyNumber && `Registered in England and Wales, company number ${site.companyNumber}`,
    site.registeredOffice && `Registered office: ${site.registeredOffice}`,
    site.vatNumber && `VAT number ${site.vatNumber}`,
  ].filter(Boolean)

  return (
    <footer className={styles.footer}>
      <Container>
        <div className={styles.grid}>
          <div className={styles.brand}>
            <Logo tone="inverse" />
            <p className={styles.blurb}>
              A UK digital agency building software, AI and cloud services for businesses and the public sector, and
              products of our own.
            </p>
            <a className={styles.email} href={`mailto:${site.email}`}>
              {site.email}
            </a>
          </div>

          {columns.map((column) => (
            <nav key={column.title} aria-label={column.title}>
              <h2 className={styles.columnTitle}>{column.title}</h2>
              <ul className={styles.links}>
                {column.links.map((link) => (
                  <li key={link.to}>
                    <Link to={link.to}>{link.label}</Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className={styles.legal}>
          <p>
            © {new Date().getFullYear()} {site.legalName}.{disclosures.length > 0 && ` ${disclosures.join('. ')}.`}
          </p>
          <Link to="/privacy">Privacy notice</Link>
        </div>
      </Container>
    </footer>
  )
}
