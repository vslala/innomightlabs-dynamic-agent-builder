import { Link } from 'react-router-dom'
import { Container } from '@/components/Container/Container'
import { PageHero } from '@/components/PageHero/PageHero'
import { Prose } from '@/components/Prose/Prose'
import { Seo } from '@/components/Seo/Seo'
import { site } from '@/content/site'
import styles from './style.module.css'

export function Privacy() {
  return (
    <>
      <Seo title="Privacy notice" description={`How ${site.legalName} collects and uses personal data on innomight.com.`} />
      <PageHero
        eyebrow="Legal"
        title="Privacy notice"
        intro="How we collect and use your personal data when you use this website or get in touch."
      />
      <section className={styles.body}>
        <Container>
          <Prose>
            <p>
              <strong>Last updated:</strong> 2 October 2026
            </p>

            <h2>Who we are</h2>
            <p>
              This website is run by {site.legalName} ("Innomight", "we", "us"), a company based in the{' '}
              {site.location}. We are the data controller for personal data collected through innomight.com. You can
              contact us about privacy at <a href={`mailto:${site.email}`}>{site.email}</a>.
            </p>

            <h2>What we collect</h2>
            <p>
              When you use our <Link to="/contact">contact form</Link> or email us, we collect your name, email address,
              organisation (if you give it) and the content of your message. Our servers also record standard technical
              information such as your IP address, which we use to prevent abuse of the contact form.
            </p>

            <h2>How we use it and why</h2>
            <p>
              We use your details only to respond to your enquiry and, if you become a client, to manage our
              relationship with you. Our lawful basis is our legitimate interest in responding to people who contact us,
              or taking steps at your request before entering into a contract. We do not sell your data or use it for
              marketing without your consent.
            </p>

            <h2>Who we share it with</h2>
            <p>
              We use trusted service providers to run this website and deliver email, including Amazon Web Services for
              hosting and Mailjet for email delivery. They process data only on our instructions.
            </p>

            <h2>How long we keep it</h2>
            <p>
              We keep enquiries for up to 24 months unless they lead to a working relationship, in which case we keep
              records for as long as the law requires.
            </p>

            <h2>Cookies</h2>
            <p>
              We do not use advertising or tracking cookies. Your browser stores your light or dark theme choice
              locally; it never leaves your device.
            </p>

            <h2>Your rights</h2>
            <p>
              Under UK data protection law you can ask to access, correct or delete your personal data, or object to how
              we use it. Email us and we will respond within one month. If you are unhappy with how we have handled your
              data, you can complain to the Information Commissioner's Office at{' '}
              <a href="https://ico.org.uk" rel="noopener">
                ico.org.uk
              </a>
              .
            </p>
          </Prose>
        </Container>
      </section>
    </>
  )
}
