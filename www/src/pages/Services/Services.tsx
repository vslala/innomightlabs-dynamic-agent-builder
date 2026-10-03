import { AccentTile } from '@/components/AccentTile/AccentTile'
import { Button } from '@/components/Button/Button'
import { Container } from '@/components/Container/Container'
import { CtaBanner } from '@/components/CtaBanner/CtaBanner'
import { Icon } from '@/components/Icon/Icon'
import { PageHero } from '@/components/PageHero/PageHero'
import { ProcessSteps } from '@/components/ProcessSteps/ProcessSteps'
import { Section } from '@/components/Section/Section'
import { Seo } from '@/components/Seo/Seo'
import { deliveryProcess } from '@/content/process'
import { services } from '@/content/services'
import styles from './style.module.css'

export function Services() {
  return (
    <>
      <Seo
        title="Services"
        description="Custom software development, AI and automation, cloud and DevOps, and public-sector delivery from Innomight Labs, a UK digital agency."
      />
      <PageHero
        eyebrow="Services"
        title="One team for software, AI, cloud and public-sector delivery"
        intro="Engage us for a focused piece of work or to take a service from discovery to live. Either way you get senior people, a clear plan and working software early."
        actions={
          <Button to="/contact" size="lg" icon="arrow-right">
            Talk to us about a project
          </Button>
        }
      />

      <nav className={styles.jumpNav} aria-label="Services on this page">
        <Container>
          <ul className={styles.jumpList}>
            {services.map((service) => (
              <li key={service.id}>
                <a href={`#${service.id}`}>{service.title}</a>
              </li>
            ))}
          </ul>
        </Container>
      </nav>

      {services.map((service, index) => (
        <section
          key={service.id}
          id={service.id}
          className={`${styles.service} ${index % 2 === 1 ? styles.alternate : ''}`}
          aria-labelledby={`${service.id}-title`}
        >
          <Container className={styles.serviceInner}>
            <div className={styles.serviceText}>
              <AccentTile icon={service.icon} accent={service.accent} />
              <h2 id={`${service.id}-title`} className={styles.serviceTitle}>
                {service.title}
              </h2>
              <p className={styles.serviceDescription}>{service.description}</p>
              <div>
                <Button to={`/contact?topic=${service.enquiryTopic}`} variant="secondary" icon="arrow-right">
                  Discuss {service.title.toLowerCase()}
                </Button>
              </div>
            </div>
            <div className={styles.capabilities}>
              <h3 className={styles.capabilitiesTitle}>What we deliver</h3>
              <ul className={styles.capabilityList}>
                {service.capabilities.map((capability) => (
                  <li key={capability}>
                    <Icon name="check" size={18} />
                    {capability}
                  </li>
                ))}
              </ul>
            </div>
          </Container>
        </section>
      ))}

      <Section
        id="how-we-work"
        tone="subtle"
        eyebrow="How we work"
        title="The same proven rhythm on every engagement"
        intro="Scaled to the size of the problem, from a two-week discovery to a multi-year programme."
      >
        <ProcessSteps steps={deliveryProcess} />
      </Section>

      <CtaBanner />
    </>
  )
}
