import { Link } from 'react-router-dom'
import { CtaBanner } from '@/components/CtaBanner/CtaBanner'
import { FeatureGrid } from '@/components/FeatureGrid/FeatureGrid'
import { PageHero } from '@/components/PageHero/PageHero'
import { Prose } from '@/components/Prose/Prose'
import { Section } from '@/components/Section/Section'
import { Seo } from '@/components/Seo/Seo'
import { principles } from '@/content/company'
import { productPath, products } from '@/content/products'
import { site } from '@/content/site'
import styles from './style.module.css'

const innomightLabs = products.find((product) => product.slug === 'innomightlabs-engram')

export function About() {
  const facts = [
    { label: 'Registered name', value: site.legalName },
    { label: 'Trading as', value: site.name },
    { label: 'Based in', value: site.location },
    { label: 'What we do', value: 'Software, AI, cloud and public-sector delivery' },
  ]

  return (
    <>
      <Seo
        title="About us"
        description={`${site.legalName} is a UK digital agency and product studio. Meet the team behind Innomight's client work and products.`}
      />
      <PageHero
        eyebrow="About us"
        title="A digital agency that builds its own products"
        intro="Innomight Labs is a UK company that designs, builds and runs software for clients, and for ourselves. That combination makes us better at both."
      />

      <Section id="story">
        <div className={styles.story}>
          <Prose>
            <h2>Our story</h2>
            <p>
              We started Innomight Labs to build software the way we always wanted to: senior engineers working closely
              with the people who will use what we make, shipping small improvements often and owning the result long
              after launch.
            </p>
            <p>
              Today we deliver projects for businesses and public bodies, bid for public-sector contracts and build
              products of our own. Running our own software in production keeps our standards high: everything we
              recommend to clients, we rely on ourselves.
            </p>
            <h3>Innomight and InnomightLabs</h3>
            <p>
              {site.legalName} trades as Innomight at innomight.com.{' '}
              {innomightLabs && (
                <>
                  <Link to={productPath(innomightLabs)}>{innomightLabs.name}</Link>, our AI agent platform at
                  innomightlabs.com, is one of the products we build and run.
                </>
              )}
            </p>
          </Prose>

          <dl className={styles.facts}>
            {facts.map((fact) => (
              <div key={fact.label} className={styles.fact}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </Section>

      <Section id="principles" tone="subtle" eyebrow="What we believe" title="How we work with every client">
        <FeatureGrid features={principles} columns={4} />
      </Section>

      <CtaBanner />
    </>
  )
}
