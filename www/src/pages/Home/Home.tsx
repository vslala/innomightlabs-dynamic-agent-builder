import { Button } from '@/components/Button/Button'
import { Container } from '@/components/Container/Container'
import { Credentials } from '@/components/Credentials/Credentials'
import { CtaBanner } from '@/components/CtaBanner/CtaBanner'
import { FeatureGrid } from '@/components/FeatureGrid/FeatureGrid'
import { HeroVisual } from '@/components/HeroVisual/HeroVisual'
import { Icon } from '@/components/Icon/Icon'
import { MediaFrame } from '@/components/MediaFrame/MediaFrame'
import { ProcessSteps } from '@/components/ProcessSteps/ProcessSteps'
import { ProductCard } from '@/components/ProductCard/ProductCard'
import { Section } from '@/components/Section/Section'
import { Seo } from '@/components/Seo/Seo'
import { ServiceCard } from '@/components/ServiceCard/ServiceCard'
import { principles, publicSectorCommitments } from '@/content/company'
import { deliveryProcess } from '@/content/process'
import { productHost, productPath, products } from '@/content/products'
import { services } from '@/content/services'
import { site } from '@/content/site'
import styles from './style.module.css'

const proofPoints = ['UK-based senior team', 'Public-sector ready', 'Our own products in production']

// The product we lead with in the "see it in action" spotlight.
const spotlight = products[0]

export function Home() {
  return (
    <>
      <Seo
        title="Software, AI and digital services"
        description={site.description}
        jsonLd={{
          '@type': 'Organization',
          name: site.legalName,
          alternateName: site.name,
          url: site.url,
          logo: `${site.url}/logo.png`,
          email: site.email,
          description: site.description,
          areaServed: 'GB',
          address: { '@type': 'PostalAddress', addressCountry: 'GB' },
        }}
      />

      <section className={styles.hero}>
        <Container className={styles.heroInner}>
          <div className={styles.heroText}>
            <p className={styles.eyebrow}>UK digital agency and product studio</p>
            <h1 className={styles.title}>
              We build the software that <span className={styles.highlight}>moves your organisation forward</span>
            </h1>
            <p className={styles.intro}>
              Innomight Labs designs, builds and runs digital services for businesses and the public sector. We bid for
              and deliver public contracts, and we build products of our own, so we know what it takes to ship.
            </p>
            <div className={styles.actions}>
              <Button to="/contact" size="lg" icon="arrow-right">
                Start a project
              </Button>
              <Button to="/software" size="lg" variant="secondary">
                Explore our software
              </Button>
            </div>
            <ul className={styles.proof}>
              {proofPoints.map((point) => (
                <li key={point}>
                  <Icon name="check" size={18} />
                  {point}
                </li>
              ))}
            </ul>
          </div>
          <HeroVisual />
        </Container>
      </section>

      <Section
        id="services"
        eyebrow="What we do"
        title="From first idea to a service people rely on"
        intro="Four practices, one team. Bring us in for a single piece of work or to deliver end to end."
        actions={
          <Button to="/services" variant="secondary" icon="arrow-right">
            All services
          </Button>
        }
      >
        <ul className={styles.serviceGrid}>
          {services.map((service) => (
            <li key={service.id}>
              <ServiceCard service={service} />
            </li>
          ))}
        </ul>
      </Section>

      <Section
        id="software"
        tone="subtle"
        eyebrow="Our software"
        title="Products built by Innomight"
        intro="We design, build and operate our own products. The same team and standards go into the work we do for clients."
        actions={
          <Button to="/software" variant="secondary" icon="arrow-right">
            View all software
          </Button>
        }
      >
        <ul className={styles.productGrid}>
          {products.map((product) => (
            <li key={product.slug}>
              <ProductCard product={product} />
            </li>
          ))}
        </ul>
      </Section>

      <Section id="spotlight">
        <div className={styles.spotlight}>
          <div className={styles.spotlightText}>
            <p className={styles.eyebrow}>See it in action</p>
            <h2 className={styles.spotlightTitle}>{spotlight.tagline}</h2>
            <p className={styles.spotlightBody}>{spotlight.summary}</p>
            <ul className={styles.checklist}>
              {spotlight.highlights.slice(0, 4).map((highlight) => (
                <li key={highlight.title}>
                  <Icon name="check" size={18} />
                  {highlight.title}
                </li>
              ))}
            </ul>
            <div className={styles.actions}>
              <Button to={productPath(spotlight)} icon="arrow-right">
                Explore {spotlight.name}
              </Button>
              <Button href={spotlight.url} variant="subtle" icon="external">
                Visit {productHost(spotlight)}
              </Button>
            </div>
          </div>
          <MediaFrame product={spotlight} />
        </div>
      </Section>

      <Section
        id="public-sector"
        tone="inverse"
        eyebrow="Public sector"
        title="A delivery partner for government and public bodies"
        intro="We bid for and deliver public-sector contracts, from short discoveries to live services, and we make procurement straightforward."
        actions={
          <>
            <Button to="/contact?topic=public-sector" variant="inverse" icon="arrow-right">
              Discuss a tender
            </Button>
            <Button to="/public-sector" variant="inverse-outline">
              How we work with the public sector
            </Button>
          </>
        }
      >
        <FeatureGrid features={publicSectorCommitments} columns={4} tone="inverse" />
        <div className={styles.credentials}>
          <Credentials />
        </div>
      </Section>

      <Section
        id="how-we-work"
        tone="subtle"
        eyebrow="How we work"
        title="A clear way of working, from first conversation to live service"
        intro="Every engagement follows the same proven rhythm, scaled to the size of the problem."
      >
        <ProcessSteps steps={deliveryProcess} />
      </Section>

      <Section id="why-innomight" eyebrow="Why Innomight" title="Why organisations choose to work with us">
        <FeatureGrid features={principles} columns={4} />
      </Section>

      <CtaBanner />
    </>
  )
}
