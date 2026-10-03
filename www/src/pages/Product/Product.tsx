import { Button } from '@/components/Button/Button'
import { CtaBanner } from '@/components/CtaBanner/CtaBanner'
import { FeatureGrid } from '@/components/FeatureGrid/FeatureGrid'
import { MediaFrame } from '@/components/MediaFrame/MediaFrame'
import { PageHero } from '@/components/PageHero/PageHero'
import { ProductStatusBadge } from '@/components/ProductStatusBadge/ProductStatusBadge'
import { Section } from '@/components/Section/Section'
import { Seo } from '@/components/Seo/Seo'
import { productHost, type Product as ProductModel } from '@/content/products'
import { site } from '@/content/site'
import styles from './style.module.css'

export function Product({ product }: { product: ProductModel }) {
  return (
    <>
      <Seo
        title={`${product.name}: ${product.category}`}
        description={product.summary}
        jsonLd={{
          '@type': 'SoftwareApplication',
          name: product.name,
          description: product.summary,
          applicationCategory: 'BusinessApplication',
          operatingSystem: 'Web',
          url: product.url,
          publisher: { '@type': 'Organization', name: site.legalName, url: site.url },
        }}
      />
      <PageHero
        eyebrow={product.category}
        title={product.name}
        intro={product.tagline}
        actions={
          <>
            <Button href={product.url} size="lg" icon="external">
              Visit {productHost(product)}
            </Button>
            <Button to="/contact?topic=product" size="lg" variant="secondary">
              Talk to us
            </Button>
          </>
        }
        aside={<MediaFrame product={product} />}
      />

      <Section id="overview">
        <div className={styles.overview}>
          <div className={styles.status}>
            <ProductStatusBadge status={product.status} />
            <span>by {site.legalName}</span>
          </div>
          <h2 className={styles.overviewTitle}>What {product.name} does</h2>
          <div className={styles.description}>
            {product.description.map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </div>
          <p className={styles.audience}>
            <strong>Built for:</strong> {product.audience}
          </p>
        </div>
      </Section>

      <Section id="features" tone="subtle" eyebrow="Features" title={`Why teams choose ${product.name}`}>
        <FeatureGrid features={product.highlights} columns={3} />
      </Section>

      <CtaBanner
        title={`Ready to try ${product.name}?`}
        body={`Get started at ${productHost(product)}, or talk to us about a demo, a pilot or tailoring ${product.name} to your organisation.`}
      />
    </>
  )
}
