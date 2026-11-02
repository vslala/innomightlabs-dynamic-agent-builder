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
              <strong>Last updated:</strong> 2 November 2026
            </p>

            <h2>Who we are</h2>
            <p>
              This website is run by {site.legalName} ("Innomight", "we", "us"), a private company limited by shares,
              registered in {site.jurisdiction} under company number {site.companyNumber}, with its registered office at{' '}
              {site.registeredOffice}. We are the data controller for personal data collected through innomight.com. You
              can contact us about privacy at <a href={`mailto:${site.email}`}>{site.email}</a>.
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
              We use trusted service providers to run this website and handle enquiries: Amazon Web Services for hosting,
              GitHub to keep a private record of each enquiry and Mailjet to send you a confirmation email. They process
              data only on our instructions.
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

            <h2 id="public-authority-requests">Requests from public authorities</h2>
            <p>
              This section covers requests from a government, court, regulator or law-enforcement agency for personal
              data about our users. That includes data we receive from platforms our users connect to our products, such
              as Meta, Google and LinkedIn.
            </p>
            <ul>
              <li>
                <strong>How to make a request.</strong> Send it in writing to{' '}
                <a href={`mailto:${site.legalEmail}`}>{site.legalEmail}</a>, or serve it on {site.legalName} at our
                registered office, {site.registeredOffice}. We disclose user data only under valid legal process (a court
                order, warrant, or a notice issued under the law that binds us), never in response to an informal
                request.
              </li>
              <li>
                <strong>We review every request for legality.</strong> Before we respond, we verify that the request is
                genuine. We check that the requester has the authority and jurisdiction to make it, the legal basis it
                relies on, that it names specific users, dates and data, and that it is necessary and proportionate. We
                also check that complying wouldn't break another law that protects our users, such as UK data
                protection law. We take legal advice when we need it.
              </li>
              <li>
                <strong>We challenge unlawful requests.</strong> If a request has no valid legal basis, or is
                overbroad, disproportionate or improperly served, we ask for it to be withdrawn or narrowed. If needed,
                we challenge it through the available legal remedies, and we disclose nothing while the challenge is
                pending where the law allows it. We also challenge non-disclosure orders that aren't justified.
              </li>
              <li>
                <strong>We disclose the minimum.</strong> We read requests narrowly and disclose only the data the
                request lawfully requires, for the users and dates it covers. We never disclose passwords or access
                tokens, including tokens issued by the platforms our users connect, and we don't create data to answer a
                request.
              </li>
              <li>
                <strong>We tell the user.</strong> Unless the law forbids it, we notify the affected user and send them a
                copy of the request before we disclose anything, so they can object. If the law forbids notice, we
                notify them as soon as the restriction ends. In a genuine emergency involving a risk of death or serious
                harm we may disclose limited data without legal process, then notify the user afterwards unless that
                would increase the risk.
              </li>
              <li>
                <strong>We document every request.</strong> We record each request, our legal assessment, the people who
                made the decision, any challenge, and what we disclosed or why we disclosed nothing. We keep these records
                for six years.
              </li>
            </ul>

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
