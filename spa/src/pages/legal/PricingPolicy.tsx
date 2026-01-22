import { Navbar } from '../../components/Navbar';
import { Footer } from '../../components/Footer';
import styles from './Legal.module.css';

export function PricingPolicy() {
  return (
    <>
      <Navbar />
      <main className={styles.page}>
        <div className={styles.container}>
          <header className={styles.header}>
            <span className={styles.eyebrow}>Legal</span>
            <h1 className={styles.title}>Pricing Policy</h1>
            <p className={styles.subtitle}>
              This policy explains how pricing, billing, and usage limits work at InnoMight Labs. It
              does not list specific prices, which may change over time.
            </p>
          </header>

          <section className={styles.section}>
            <h2>1. Plans and Usage Limits</h2>
            <p>
              We offer multiple plans with different usage limits and features. Each plan defines
              monthly limits for things like agents, messages, and knowledge base pages. Limits are
              enforced automatically to protect platform reliability.
            </p>
          </section>

          <section className={styles.section}>
            <h2>2. Subscription Billing</h2>
            <p>
              Subscriptions renew automatically at the end of each billing cycle unless cancelled.
              Your billing cycle and renewal date are shown in your account settings.
            </p>
            <p>
              If a payment fails, your subscription may enter a grace period. Continued access
              depends on payment resolution.
            </p>
          </section>

          <section className={styles.section}>
            <h2>3. Upgrades and Downgrades</h2>
            <p>
              Upgrades take effect immediately. Downgrades may take effect at the next billing
              cycle to avoid disrupting active usage. If your usage exceeds the limits of a lower
              tier, we will prompt you to adjust usage before the downgrade takes effect.
            </p>
          </section>

          <section className={styles.section}>
            <h2>4. Taxes and Fees</h2>
            <p>
              Prices are shown exclusive of applicable taxes unless stated otherwise. Taxes or
              other government fees may be added based on your location.
            </p>
          </section>

          <section className={styles.section}>
            <h2>5. Refunds</h2>
            <p>
              Fees are generally non-refundable. If you believe a billing error occurred, contact
              us within 30 days and we will review your request.
            </p>
          </section>

          <section className={styles.section}>
            <h2>6. Changes to Pricing</h2>
            <p>
              We may update pricing, plan features, or limits from time to time. We will provide
              notice for material changes before they take effect.
            </p>
          </section>

          <section className={styles.section}>
            <h2>7. Contact</h2>
            <p>
              Questions about pricing? Email{' '}
              <a className={styles.link} href="mailto:billing@innomightlabs.com">
                billing@innomightlabs.com
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
