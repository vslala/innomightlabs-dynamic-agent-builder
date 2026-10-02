import { Link } from 'react-router-dom'
import { Head } from 'vite-react-ssg'
import { products } from '../products'

export default function Home() {
  return (
    <>
      <Head>
        <title>Innomight Labs — Software and digital delivery</title>
        <meta
          name="description"
          content="Innomight Labs is a UK digital agency building software products and delivering solutions for clients."
        />
      </Head>
      <section className="mx-auto max-w-6xl px-6 py-24">
        <h1 className="max-w-3xl text-5xl font-semibold tracking-tight">
          We build software that does the heavy lifting.
        </h1>
        <p className="mt-6 max-w-2xl text-lg text-[var(--text-secondary)]">
          Innomight Labs is a UK digital agency. We design, build and run software for our clients — and our own
          products.
        </p>
      </section>
      <section className="mx-auto grid max-w-6xl gap-6 px-6 pb-24 sm:grid-cols-2">
        {products.map((product) => (
          <Link
            key={product.name}
            to={product.page}
            className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-panel)] p-8 hover:bg-[var(--surface-panel-hover)]"
          >
            <h2 className="text-2xl font-semibold">{product.name}</h2>
            <p className="mt-2 text-[var(--text-secondary)]">{product.tagline}</p>
          </Link>
        ))}
      </section>
    </>
  )
}
