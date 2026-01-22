import { Navbar } from '../../components/Navbar';
import { Footer } from '../../components/Footer';
import styles from './Legal.module.css';

export function Terms() {
  return (
    <>
      <Navbar />
      <main className={styles.page}>
        <div className={styles.container}>
          <header className={styles.header}>
            <span className={styles.eyebrow}>Legal</span>
            <h1 className={styles.title}>Terms of Service</h1>
            <p className={styles.subtitle}>
              These terms govern your use of InnoMight Labs. By creating an account or using the
              service, you agree to the terms below.
            </p>
          </header>

          <section className={styles.section}>
            <h2>1. Acceptance of Terms</h2>
            <p>
              By accessing or using the platform, you confirm that you have read, understood, and
              agree to these Terms of Service. If you are using the platform on behalf of an
              organization, you represent that you have the authority to bind that organization.
            </p>
          </section>

          <section className={styles.section}>
            <h2>2. Accounts and Access</h2>
            <p>
              You are responsible for maintaining the confidentiality of your account credentials
              and for all activity under your account. Notify us immediately if you suspect
              unauthorized access.
            </p>
            <p>
              We may suspend or terminate access if we reasonably believe your use violates these
              terms or harms the platform, other users, or third parties.
            </p>
          </section>

          <section className={styles.section}>
            <h2>3. Acceptable Use</h2>
            <p>
              You agree not to misuse the platform, including by attempting to gain unauthorized
              access, disrupting service integrity, or using the service to violate applicable laws.
            </p>
            <ul>
              <li>Do not upload or transmit malicious code or harmful content.</li>
              <li>Do not reverse engineer or attempt to extract proprietary source code.</li>
              <li>Do not use the service to create or distribute illegal or abusive material.</li>
            </ul>
          </section>

          <section className={styles.section}>
            <h2>4. User Content and Data</h2>
            <p>
              You retain ownership of content you provide to the platform. You grant us a limited
              license to process that content solely to operate and improve the service.
            </p>
            <p>
              You are responsible for ensuring that your content complies with applicable laws and
              does not infringe the rights of others.
            </p>
          </section>

          <section className={styles.section}>
            <h2>5. Service Availability</h2>
            <p>
              We strive to keep the service available, but we do not guarantee uninterrupted
              operation. Maintenance, outages, or third-party issues may affect availability.
            </p>
          </section>

          <section className={styles.section}>
            <h2>6. Paid Plans and Billing</h2>
            <p>
              Paid features are billed on a recurring basis. Your subscription renews unless
              cancelled before the renewal date. We may update plan features or limits, and we will
              communicate material changes in advance.
            </p>
            <p>
              You are responsible for all charges incurred under your account. Taxes may apply
              depending on your location.
            </p>
          </section>

          <section className={styles.section}>
            <h2>7. Termination</h2>
            <p>
              You may cancel your subscription at any time. Upon termination, access to paid
              features will end at the conclusion of your current billing period.
            </p>
            <p>
              We may suspend or terminate your account for material violations of these terms or to
              comply with legal obligations.
            </p>
          </section>

          <section className={styles.section}>
            <h2>8. Disclaimer and Limitation of Liability</h2>
            <p>
              The service is provided on an “as is” and “as available” basis. To the maximum extent
              permitted by law, we disclaim all warranties and will not be liable for indirect,
              incidental, or consequential damages.
            </p>
          </section>

          <section className={styles.section}>
            <h2>9. Changes to These Terms</h2>
            <p>
              We may update these terms from time to time. If we make material changes, we will
              notify you through the platform or by email.
            </p>
          </section>

          <section className={styles.section}>
            <h2>10. Contact</h2>
            <p>
              Questions about these terms? Reach out at{' '}
              <a className={styles.link} href="mailto:support@innomightlabs.com">
                support@innomightlabs.com
              </a>
              .
            </p>
          </section>

          <p className={styles.note}>Last updated: January 21, 2026</p>
        </div>
      </main>
      <Footer />
    </>
  );
}
