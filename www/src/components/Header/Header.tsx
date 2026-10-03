import { useEffect, useRef } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { AccentTile } from '@/components/AccentTile/AccentTile'
import { Button } from '@/components/Button/Button'
import { Container } from '@/components/Container/Container'
import { Icon } from '@/components/Icon/Icon'
import { Logo } from '@/components/Logo/Logo'
import { ProductStatusBadge } from '@/components/ProductStatusBadge/ProductStatusBadge'
import { ThemeToggle } from '@/components/ThemeToggle/ThemeToggle'
import { primaryNav } from '@/content/navigation'
import { productPath, products } from '@/content/products'
import { useDisclosure } from '@/hooks/useDisclosure'
import styles from './style.module.css'

const navLinkClass = ({ isActive }: { isActive: boolean }) => `${styles.navLink} ${isActive ? styles.active : ''}`

export function Header() {
  const productsMenuRef = useRef<HTMLDivElement>(null)
  const productsMenu = useDisclosure(productsMenuRef)
  const mobileMenu = useDisclosure()

  // Stop the page scrolling behind the full-screen mobile menu.
  useEffect(() => {
    document.body.style.overflow = mobileMenu.isOpen ? 'hidden' : ''
  }, [mobileMenu.isOpen])

  return (
    <header className={styles.header}>
      <Container className={styles.bar}>
        <Link to="/" className={styles.home} aria-label="Innomight Labs home">
          <Logo />
        </Link>

        <nav className={styles.desktopNav} aria-label="Main">
          <div className={styles.menu} ref={productsMenuRef}>
            <button
              type="button"
              className={`${styles.navLink} ${styles.menuButton}`}
              aria-expanded={productsMenu.isOpen}
              aria-controls="products-menu"
              onClick={productsMenu.toggle}
            >
              Software
              <Icon name="chevron-down" size={16} className={styles.chevron} />
            </button>
            <div id="products-menu" className={styles.menuPanel} hidden={!productsMenu.isOpen}>
              <p className={styles.menuHeading}>Our products</p>
              <ul className={styles.productList}>
                {products.map((product) => (
                  <li key={product.slug}>
                    <Link to={productPath(product)} className={styles.productLink}>
                      <AccentTile icon={product.icon} accent={product.accent} size="sm" />
                      <span className={styles.productText}>
                        <span className={styles.productName}>
                          {product.name}
                          <ProductStatusBadge status={product.status} />
                        </span>
                        <span className={styles.productTagline}>{product.tagline}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
              <Link to="/software" className={styles.menuFooter}>
                View all software <Icon name="arrow-right" size={16} />
              </Link>
            </div>
          </div>
          {primaryNav.map((item) => (
            <NavLink key={item.to} to={item.to} className={navLinkClass}>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className={styles.actions}>
          <ThemeToggle />
          <span className={styles.desktopOnly}>
            <Button to="/contact">Contact us</Button>
          </span>
          <button
            type="button"
            className={styles.mobileToggle}
            aria-expanded={mobileMenu.isOpen}
            aria-controls="mobile-menu"
            aria-label={mobileMenu.isOpen ? 'Close menu' : 'Open menu'}
            onClick={mobileMenu.toggle}
          >
            <Icon name={mobileMenu.isOpen ? 'close' : 'menu'} size={24} />
          </button>
        </div>
      </Container>

      <div id="mobile-menu" className={styles.mobilePanel} hidden={!mobileMenu.isOpen}>
        <Container>
          <nav aria-label="Mobile">
            <p className={styles.menuHeading}>Software</p>
            <ul className={styles.mobileList}>
              {products.map((product) => (
                <li key={product.slug}>
                  <Link to={productPath(product)} className={styles.mobileProduct}>
                    <AccentTile icon={product.icon} accent={product.accent} size="sm" />
                    <span>
                      <span className={styles.productName}>{product.name}</span>
                      <span className={styles.productTagline}>{product.category}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
            <ul className={styles.mobileList}>
              {[{ label: 'All software', to: '/software' }, ...primaryNav].map((item) => (
                <li key={item.to}>
                  <NavLink to={item.to} className={styles.mobileLink}>
                    {item.label}
                    <Icon name="arrow-right" size={18} />
                  </NavLink>
                </li>
              ))}
            </ul>
            <Button to="/contact" size="lg">
              Contact us
            </Button>
          </nav>
        </Container>
      </div>
    </header>
  )
}
