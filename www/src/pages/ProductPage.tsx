import { Head } from 'vite-react-ssg'
import type { Product } from '../products'

export default function ProductPage({ product }: { product: Product }) {
  return (
    <>
      <Head>
        <title>{`${product.name} — Innomight Labs`}</title>
        <meta name="description" content={product.tagline} />
      </Head>
      <section className="mx-auto max-w-6xl px-6 py-24">
        <p className="text-sm uppercase tracking-widest text-[var(--text-muted)]">A product by Innomight Labs</p>
        <h1 className="mt-3 text-5xl font-semibold tracking-tight">{product.name}</h1>
        <p className="mt-6 max-w-2xl text-lg text-[var(--text-secondary)]">{product.tagline}</p>
        <a
          href={product.appUrl}
          className="mt-10 inline-block rounded-lg bg-[var(--button-primary-bg)] px-6 py-3 font-medium text-[var(--text-inverse)] hover:bg-[var(--button-primary-bg-hover)]"
        >
          Go to {product.name}
        </a>
      </section>
    </>
  )
}
