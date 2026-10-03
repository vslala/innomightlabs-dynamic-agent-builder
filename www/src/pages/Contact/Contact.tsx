import { useSearchParams } from 'react-router-dom'
import { ContactForm } from '@/components/ContactForm/ContactForm'
import { Container } from '@/components/Container/Container'
import { Icon } from '@/components/Icon/Icon'
import { Seo } from '@/components/Seo/Seo'
import { site } from '@/content/site'
import { enquiryTopics, type EnquiryTopic } from '@/services/contact/contactService'
import styles from './style.module.css'

const nextSteps = [
  'We read every message and reply within two working days.',
  'A short call to understand your goals, timescales and constraints.',
  'A clear proposal, or honest advice if we are not the right fit.',
]

function isEnquiryTopic(value: string | null): value is EnquiryTopic {
  return value !== null && value in enquiryTopics
}

export function Contact() {
  const [searchParams] = useSearchParams()
  const topic = searchParams.get('topic')

  return (
    <>
      <Seo
        title="Contact us"
        description="Talk to Innomight Labs about a software project, a public-sector tender, our products or a partnership. We reply within two working days."
      />
      <section className={styles.page}>
        <Container className={styles.inner}>
          <div className={styles.intro}>
            <p className={styles.eyebrow}>Contact</p>
            <h1 className={styles.title}>Let's talk about what you're building</h1>
            <p className={styles.lead}>
              Whether it is a new project, a tender, one of our products or something else, tell us a little about it and
              the right person will get back to you.
            </p>

            <ul className={styles.details}>
              <li>
                <Icon name="mail" />
                <a href={`mailto:${site.email}`}>{site.email}</a>
              </li>
              <li>
                <Icon name="map-pin" />
                {site.legalName}, {site.location}
              </li>
            </ul>

            <div className={styles.next}>
              <h2 className={styles.nextTitle}>What happens next</h2>
              <ol className={styles.steps}>
                {nextSteps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </div>
          </div>

          <div className={styles.card}>
            <ContactForm topic={isEnquiryTopic(topic) ? topic : undefined} />
          </div>
        </Container>
      </section>
    </>
  )
}
