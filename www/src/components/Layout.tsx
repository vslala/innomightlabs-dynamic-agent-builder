import { useState } from 'react'
import { Link, Outlet } from 'react-router-dom'
import { products } from '../products'

export default function Layout() {
  const [productsOpen, setProductsOpen] = useState(false)

  return (
    <div className="flex min-h-screen flex-col bg-[var(--surface-page)] text-[var(--text-primary)]">
      <header className="sticky top-0 z-10 border-b border-[var(--border-subtle)] bg-[var(--surface-page)]/90 backdrop-blur">
        <nav className="mx-auto flex max-w-6xl items-center gap-8 px-6 py-4">
          <Link to="/" className="text-lg font-semibold tracking-tight">
            Innomight Labs
          </Link>
          <div className="relative" onMouseLeave={() => setProductsOpen(false)}>
            <button
              type="button"
              className="text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              aria-expanded={productsOpen}
              onClick={() => setProductsOpen((open) => !open)}
              onMouseEnter={() => setProductsOpen(true)}
            >
              Products ▾
            </button>
            {productsOpen && (
              <div className="absolute left-0 top-full w-80 pt-3">
                <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-popover)] p-2 shadow-xl">
                  {products.map((product) => (
                    <Link
                      key={product.name}
                      to={product.page}
                      className="block rounded-lg p-3 hover:bg-[var(--surface-panel-hover)]"
                      onClick={() => setProductsOpen(false)}
                    >
                      <div className="font-medium">{product.name}</div>
                      <div className="text-sm text-[var(--text-muted)]">{product.tagline}</div>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
          <Link to="/about" className="text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
            About
          </Link>
        </nav>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-[var(--border-subtle)] text-sm text-[var(--text-muted)]">
        <div className="mx-auto max-w-6xl px-6 py-8">
          {/* UK trading disclosures: replace the placeholders with the Companies House details. */}
          <p>Innomight Labs Ltd · Registered in England and Wales · Company No. 00000000</p>
          <p>Registered office: [registered office address]</p>
        </div>
      </footer>
    </div>
  )
}
