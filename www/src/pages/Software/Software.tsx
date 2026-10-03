import { Button } from '@/components/Button/Button'
import { CtaBanner } from '@/components/CtaBanner/CtaBanner'
import { PageHero } from '@/components/PageHero/PageHero'
import { ProductCard } from '@/components/ProductCard/ProductCard'
import { Section } from '@/components/Section/Section'
import { Seo } from '@/components/Seo/Seo'
import { products } from '@/content/products'
import styles from './style.module.css'

export function Software() {
  return (
    <>
      <Seo
        title="Software"
        description={`Products built and run by Innomight Labs: ${products.map((product) => `${product.name}, ${product.category.toLowerCase()}`).join('; ')}.`}
      />
      <PageHero
        eyebrow="Software"
        title="Products built and run by Innomight"
        intro="We build products for problems we understand first-hand, then run them in production every day. Each one is backed by the same team that builds software for our clients."
      />

      <Section id="products">
        <ul className={styles.grid}>
          {products.map((product) => (
            <li key={product.slug}>
              <ProductCard product={product} />
            </li>
          ))}
        </ul>
      </Section>

      <Section
        id="partner"
        tone="subtle"
        eyebrow="More on the way"
        title="Have a product idea that needs a team?"
        intro="We co-build products with founders and organisations who know their market, from first prototype to launch and beyond."
        actions={
          <Button to="/contact?topic=partnership" variant="secondary" icon="arrow-right">
            Partner with us
          </Button>
        }
      />

      <CtaBanner />
    </>
  )
}
