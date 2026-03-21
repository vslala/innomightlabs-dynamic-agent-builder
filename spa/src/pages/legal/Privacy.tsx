import { Navbar } from '../../components/Navbar';
import { Footer } from '../../components/Footer';
import styles from './Legal.module.css';

export function Privacy() {
  return (
    <>
      <Navbar />
      <main className={styles.page}>
        <div className={styles.container}>
          <header className={styles.header}>
            <span className={styles.eyebrow}>Legal</span>
            <h1 className={styles.title}>Privacy Policy</h1>
            <p className={styles.subtitle}>
              This Privacy Policy explains how InnoMight Labs collects, uses, and protects
              information when you use our website and platform, including optional integrations
              like Google Drive.
            </p>
          </header>

          <section className={styles.section}>
            <h2>1. Who We Are</h2>
            <p>
              InnoMight Labs (“InnoMight Labs”, “we”, “us”) provides a platform that lets users
              build and run AI agents. This policy describes our practices when you interact with
              the service.
            </p>
          </section>

          <section className={styles.section}>
            <h2>2. Information We Collect</h2>
            <p>We may collect the following categories of information:</p>
            <ul>
              <li>
                <strong>Account information:</strong> such as your email address and basic profile
                information.
              </li>
              <li>
                <strong>Usage information:</strong> such as interactions with the product, feature
                usage, and performance metrics.
              </li>
              <li>
                <strong>Content you provide:</strong> messages, prompts, files, and other data you
                upload or connect to the platform.
              </li>
              <li>
                <strong>Payment information:</strong> if you subscribe to a paid plan, billing may
                be processed by our payment provider. We do not store full payment card details.
              </li>
            </ul>
          </section>

          <section className={styles.section}>
            <h2>3. Google Drive Integration</h2>
            <p>
              If you choose to connect Google Drive, you authorize the platform to access files you
              select or permit through Google’s OAuth permission screen.
            </p>
            <p>
              We use Google Drive access to enable agent features such as searching, reading, and
              summarizing content to provide curated answers.
            </p>
            <ul>
              <li>
                We only access Google Drive data to provide the integration features you request.
              </li>
              <li>
                You can revoke access at any time from your Google Account settings or within the
                InnoMight Labs product if available.
              </li>
              <li>
                We do not sell Google Drive data.
              </li>
            </ul>
          </section>

          <section className={styles.section}>
            <h2>4. How We Use Information</h2>
            <p>We use information to:</p>
            <ul>
              <li>Provide, maintain, and improve the platform.</li>
              <li>Operate AI agent features, including memory, tools, and integrations.</li>
              <li>Secure the service, prevent abuse, and enforce policies.</li>
              <li>Communicate with you about updates, billing, and support requests.</li>
            </ul>
          </section>

          <section className={styles.section}>
            <h2>5. How We Share Information</h2>
            <p>
              We do not sell your personal information. We may share information with:
            </p>
            <ul>
              <li>
                <strong>Service providers</strong> (e.g., hosting, analytics, payment processing)
                that help us operate the platform.
              </li>
              <li>
                <strong>Integration providers</strong> (e.g., Google) when you enable an
                integration.
              </li>
              <li>
                <strong>Legal/compliance</strong> if required to comply with applicable law,
                protect rights, or prevent fraud/abuse.
              </li>
            </ul>
          </section>

          <section className={styles.section}>
            <h2>6. Data Retention</h2>
            <p>
              We retain data for as long as necessary to provide the service, comply with legal
              obligations, resolve disputes, and enforce agreements. Retention periods may vary
              based on data type and configuration.
            </p>
          </section>

          <section className={styles.section}>
            <h2>7. Security</h2>
            <p>
              We use reasonable administrative, technical, and organizational safeguards designed to
              protect information. No method of transmission or storage is completely secure, so we
              cannot guarantee absolute security.
            </p>
          </section>

          <section className={styles.section}>
            <h2>8. Your Choices</h2>
            <ul>
              <li>Access, update, or delete your account information where available.</li>
              <li>Disconnect third-party integrations such as Google Drive.</li>
              <li>
                Contact us to request deletion of your account and associated data, subject to legal
                and operational requirements.
              </li>
            </ul>
          </section>

          <section className={styles.section}>
            <h2>9. International Transfers</h2>
            <p>
              Depending on where you live, your information may be processed in countries with
              different data protection laws than your country of residence.
            </p>
          </section>

          <section className={styles.section}>
            <h2>10. Changes to This Policy</h2>
            <p>
              We may update this policy from time to time. If we make material changes, we will
              provide notice through the platform or by email.
            </p>
          </section>

          <section className={styles.section}>
            <h2>11. Contact</h2>
            <p>
              For privacy questions or requests, email{' '}
              <a className={styles.link} href="mailto:privacy@innomightlabs.com">
                privacy@innomightlabs.com
              </a>
              .
            </p>
          </section>

          <p className={styles.note}>Last updated: March 21, 2026</p>
        </div>
      </main>
      <Footer />
    </>
  );
}
