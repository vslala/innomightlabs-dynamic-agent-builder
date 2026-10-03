import { Link } from 'react-router-dom'
import { Button } from '@/components/Button/Button'
import { Credentials } from '@/components/Credentials/Credentials'
import { CtaBanner } from '@/components/CtaBanner/CtaBanner'
import { FeatureGrid } from '@/components/FeatureGrid/FeatureGrid'
import { PageHero } from '@/components/PageHero/PageHero'
import { ProcessSteps } from '@/components/ProcessSteps/ProcessSteps'
import { Section } from '@/components/Section/Section'
import { Seo } from '@/components/Seo/Seo'
import { buyingRoutes, publicSectorCommitments, servicePhases } from '@/content/company'
import { productPath, products } from '@/content/products'
import styles from './style.module.css'

const bidSignal = products.find((product) => product.slug === 'bidsignal')

export function PublicSector() {
  return (
    <>
      <Seo
        title="Public sector"
        description="Innomight Labs bids for and delivers public-sector digital contracts: discovery to live, built to the GOV.UK Service Standard and WCAG 2.2 AA."
      />
      <PageHero
        eyebrow="Public sector"
        title="Digital services for the public sector, delivered properly"
        intro="We help government departments, local authorities, the NHS and other public bodies design, build and run services that work for everyone who needs them."
        actions={
          <>
            <Button to="/contact?topic=public-sector" size="lg" icon="arrow-right">
              Discuss a tender or contract
            </Button>
            <Button to="/services" size="lg" variant="secondary">
              Our services
            </Button>
          </>
        }
      />

      <Section
        id="commitments"
        eyebrow="Our commitments"
        title="What you can expect from us"
        intro="The standards public services are held to are the standards we build to."
      >
        <FeatureGrid features={publicSectorCommitments} columns={4} />
        <div className={styles.credentials}>
          <Credentials />
        </div>
      </Section>

      <Section
        id="phases"
        tone="subtle"
        eyebrow="Agile delivery"
        title="Discovery to live, at the pace the service needs"
        intro="We can take on a single phase or the whole journey, and work alongside your in-house teams throughout."
      >
        <ProcessSteps steps={servicePhases} />
      </Section>

      <Section
        id="buying"
        eyebrow="Working with us"
        title="Simple ways to buy from us"
        intro="We are a small, responsive supplier, which makes us easy to engage and easy to work with."
      >
        <FeatureGrid features={buyingRoutes} columns={3} />
        {bidSignal && (
          <aside className={styles.callout}>
            <p>
              <strong>We know procurement from the inside.</strong> We built{' '}
              <Link to={productPath(bidSignal)}>{bidSignal.name}</Link> to find and qualify the tenders we bid for
              ourselves, and now other suppliers use it too.
            </p>
          </aside>
        )}
      </Section>

      <CtaBanner
        title="Preparing a procurement or looking for a delivery partner?"
        body="Tell us about the opportunity. We'll come back within two working days with how we could help and the questions worth asking early."
      />
    </>
  )
}
