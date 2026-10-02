import { Head } from 'vite-react-ssg'

export default function About() {
  return (
    <>
      <Head>
        <title>About — Innomight Labs</title>
        <meta name="description" content="About Innomight Labs, a UK digital agency." />
      </Head>
      <section className="mx-auto max-w-3xl px-6 py-24">
        <h1 className="text-4xl font-semibold tracking-tight">About Innomight Labs</h1>
        <p className="mt-6 text-lg text-[var(--text-secondary)]">
          Innomight Labs Ltd is a UK digital agency that builds software solutions for clients, including public-sector
          organisations, alongside its own products.
        </p>
      </section>
    </>
  )
}
