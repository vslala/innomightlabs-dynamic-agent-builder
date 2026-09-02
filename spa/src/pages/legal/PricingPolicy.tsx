import { Footer } from '../../components/Footer';
import { Navbar } from '../../components/Navbar';
import styles from './Legal.module.css';

const sections = [
  { id: 'plans-and-prices', label: 'Plans and prices' },
  { id: 'billing-cycles', label: 'Billing cycles' },
  { id: 'free-plan', label: 'Free plan and card requirement' },
  { id: 'usage-limits', label: 'Usage limits' },
  { id: 'plan-changes', label: 'Changing plans' },
  { id: 'renewal-and-cancellation', label: 'Renewal and cancellation' },
  { id: 'payments', label: 'Payments and failed charges' },
  { id: 'taxes-and-currency', label: 'Taxes and currency' },
  { id: 'promotions', label: 'Promotions' },
  { id: 'refunds', label: 'Refunds and billing errors' },
  { id: 'enterprise', label: 'Enterprise plans' },
  { id: 'pricing-changes', label: 'Changes to pricing' },
  { id: 'contact', label: 'Contact us' },
];

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
              This policy explains how InnoMight Labs plans, subscriptions, usage limits,
              renewals, cancellations, and billing adjustments work. Current prices and included
              features are published separately on our Pricing page.
            </p>
            <time className={styles.updated} dateTime="2026-09-02">
              Effective September 2, 2026
            </time>
          </header>

          <div className={styles.documentLayout}>
            <nav className={styles.sideNav} aria-label="Pricing policy sections">
              <span className={styles.navTitle}>On this page</span>
              <ul className={styles.navList}>
                {sections.map((section) => (
                  <li key={section.id}>
                    <a className={styles.navLink} href={`#${section.id}`}>
                      {section.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>

            <article className={styles.content}>
              <section className={styles.overview} aria-labelledby="pricing-policy-overview">
                <h2 id="pricing-policy-overview">Pricing policy overview</h2>
                <p>
                  InnoMight Labs offers free, paid, and custom plans for creating and operating AI
                  agents and workflows. The price and capacity of each plan are shown before you
                  subscribe.
                </p>
                <ul>
                  <li>Paid plans are available with monthly or annual billing.</li>
                  <li>Annual plans are billed for the full annual period unless stated otherwise.</li>
                  <li>Subscriptions renew automatically until cancelled.</li>
                  <li>Usage is capped at the published plan limits; we do not charge usage overages.</li>
                  <li>Cancellation takes effect at the end of the current paid billing period.</li>
                </ul>
              </section>

              <section className={styles.section} id="plans-and-prices">
                <h2>Plans, prices, and included features</h2>
                <p>
                  Our current plans, prices, included features, and capacity limits are displayed
                  on the{' '}
                  <a className={styles.link} href="/pricing">
                    InnoMight Labs Pricing page
                  </a>
                  . The Pricing page is the current product catalogue; this policy explains the
                  rules governing purchases and subscriptions without duplicating prices that may
                  change.
                </p>
                <p>
                  Features may differ by plan and may include limits for active agents, monthly
                  messages, knowledge-base pages, memory blocks, support, or other capabilities.
                  “Unlimited” means that no fixed product quota is currently published for that
                  item, but use remains subject to our Terms of Service, acceptable-use controls,
                  technical safeguards, and reasonable measures needed to protect service
                  reliability.
                </p>
                <p>
                  The plan name, billing cycle, amount, and any applicable discount shown at
                  checkout control your purchase. Review those details before confirming payment.
                </p>
              </section>

              <section className={styles.section} id="billing-cycles">
                <h2>Monthly and annual billing cycles</h2>
                <h3>Monthly subscriptions</h3>
                <p>
                  A monthly subscription is charged at the beginning of each monthly subscription
                  period and renews monthly until cancelled.
                </p>

                <h3>Annual subscriptions</h3>
                <p>
                  An annual subscription is charged at the beginning of each annual subscription
                  period and renews annually until cancelled. The annual price shown on the Pricing
                  page is the total charge for the year, not a monthly instalment, unless checkout
                  expressly states otherwise.
                </p>
                <p>
                  When the Pricing page advertises an annual saving, it compares the displayed
                  annual price with the cost of paying the then-current monthly price for twelve
                  months. Rounding, promotions, taxes, or future price changes may affect that
                  comparison.
                </p>
              </section>

              <section className={styles.section} id="free-plan">
                <h2>Free plan and card requirement</h2>
                <p>
                  The Free plan has a subscription price of zero and includes the limits shown on
                  the Pricing page. We currently require a valid payment card when starting the
                  Free plan to verify the account and help prevent automated abuse and duplicate
                  free-plan enrollment.
                </p>
                <p>
                  We do not charge a subscription fee while your selected plan is displayed as
                  $0. Our payment processor may validate the payment method as part of its normal
                  card-verification process. A paid subscription begins only after you select a
                  paid plan and confirm the price through checkout.
                </p>
              </section>

              <section className={styles.section} id="usage-limits">
                <h2>Usage limits and measurement</h2>
                <p>
                  Each plan includes the limits displayed on the Pricing page. Some limits measure
                  currently active resources, such as agents, while monthly consumption limits,
                  such as messages and knowledge-base pages, are measured by calendar month unless
                  the product states otherwise.
                </p>
                <p>
                  When you reach a limit, the affected action may be paused or blocked until the
                  applicable limit resets, you reduce active usage, or you move to a plan with more
                  capacity. InnoMight Labs currently caps usage rather than automatically billing
                  overage charges.
                </p>
                <p>
                  Failed or retried operations may still use underlying computing resources.
                  Where the product provides a usage correction for a service-side failure, that
                  correction will appear in the relevant usage record. We do not guarantee a
                  correction when an operation completed but its result did not meet your
                  expectations.
                </p>
              </section>

              <section className={styles.section} id="plan-changes">
                <h2>Upgrades and downgrades</h2>
                <p>
                  Available plan-change options are displayed in the product or during checkout.
                  The confirmation screen will show the new plan, the amount due, and when the
                  change takes effect. Depending on the change, it may take effect immediately or
                  at the next renewal date.
                </p>
                <p>
                  A downgrade may reduce feature access or capacity. Before a downgrade takes
                  effect, you may need to reduce active agents, stored knowledge, memory blocks, or
                  other usage to fit within the lower plan. We will not automatically delete your
                  content solely because you requested a downgrade, but some actions may remain
                  unavailable while usage exceeds the new limit.
                </p>
                <p>
                  If a plan change is unavailable through the Pricing page or account settings,
                  contact billing support rather than purchasing a second subscription.
                </p>
              </section>

              <section className={styles.section} id="renewal-and-cancellation">
                <h2>Automatic renewal and cancellation</h2>
                <p>
                  Paid subscriptions renew automatically for the same billing-cycle length unless
                  you cancel before the renewal date. Renewal is charged to the saved payment
                  method at the price applicable to your subscription at that time, subject to any
                  notice required for a material price change.
                </p>
                <p>
                  You can schedule cancellation from your account settings. Cancellation prevents
                  the next renewal charge, and paid access continues until the end of the current
                  billing period. Except where required by law or expressly stated otherwise,
                  cancelling does not create a prorated refund for the remaining period.
                </p>
                <p>
                  Account deletion and subscription cancellation are related but distinct actions.
                  Before deleting an account, verify in account settings that any paid
                  subscription is cancelled. Keep the cancellation confirmation for your records.
                </p>
              </section>

              <section className={styles.section} id="payments">
                <h2>Payment processing and failed charges</h2>
                <p>
                  Stripe processes online subscription payments for InnoMight Labs. Payment-card
                  details are submitted to Stripe rather than stored directly by InnoMight Labs.
                  Stripe&apos;s terms and privacy practices also apply to its processing.
                </p>
                <p>
                  You authorize us and our payment processor to charge the payment method provided
                  for the selected subscription, renewals, applicable taxes, and other amounts
                  clearly confirmed by you. You are responsible for keeping payment and billing
                  information current.
                </p>
                <p>
                  If a payment fails, the payment processor may retry the charge and we may notify
                  you. Access to paid features may be limited or suspended if payment remains
                  unresolved. Resolving payment does not guarantee recovery of work that could not
                  run while paid access was unavailable.
                </p>
              </section>

              <section className={styles.section} id="taxes-and-currency">
                <h2>Currency, taxes, and fees</h2>
                <p>
                  Prices displayed with a dollar sign are in United States dollars unless the
                  Pricing page or checkout identifies another currency. Your bank or card provider
                  may apply currency-conversion or international-transaction fees that are not
                  charged or controlled by InnoMight Labs.
                </p>
                <p>
                  Published prices exclude applicable sales tax, VAT, GST, withholding tax, or
                  similar government charges unless stated otherwise. Any tax collected with your
                  purchase will be shown at checkout or on the applicable receipt or invoice.
                </p>
              </section>

              <section className={styles.section} id="promotions">
                <h2>Promotions, discounts, and credits</h2>
                <p>
                  We may offer promotional codes, trials, discounts, or credits with separate
                  eligibility, duration, and redemption conditions. Unless the offer says
                  otherwise, promotions cannot be combined, transferred, exchanged for cash, or
                  applied retroactively.
                </p>
                <p>
                  A temporary discount does not change the standard renewal price shown for the
                  subscription unless the promotion expressly applies to renewals. We may refuse or
                  reverse a promotion obtained through error, fraud, duplication, or violation of
                  its stated conditions.
                </p>
              </section>

              <section className={styles.section} id="refunds">
                <h2>Refunds and billing errors</h2>
                <p>
                  Subscription fees are generally non-refundable once charged, except where this
                  policy, an order, a written offer, or applicable law provides otherwise. This
                  does not limit any mandatory cancellation, withdrawal, refund, or consumer rights
                  available in your jurisdiction.
                </p>
                <p>
                  If you believe a charge is duplicated, unauthorized, or otherwise incorrect,
                  contact us as soon as possible and preferably within 30 days of the charge. Give
                  us the account email, charge date, amount, and relevant receipt or invoice
                  details. The 30-day request is intended to help us investigate promptly and does
                  not shorten a longer period provided by applicable law.
                </p>
                <p>
                  Approved refunds are ordinarily returned to the original payment method.
                  Processing time is controlled partly by the payment provider and your financial
                  institution.
                </p>
              </section>

              <section className={styles.section} id="enterprise">
                <h2>Enterprise and custom plans</h2>
                <p>
                  Enterprise plans may use negotiated pricing, invoicing, payment schedules,
                  capacity, support, security commitments, or other terms documented in an order
                  form or separate agreement. If a signed agreement conflicts with this policy,
                  the signed agreement controls for the covered purchase.
                </p>
              </section>

              <section className={styles.section} id="pricing-changes">
                <h2>Changes to plans, prices, and this policy</h2>
                <p>
                  We may introduce or discontinue plans and change prices, features, or limits as
                  the service evolves. Changes may apply immediately to new purchases. For an
                  existing paid subscription, a material price change will ordinarily apply at a
                  future renewal after any notice required by applicable law.
                </p>
                <p>
                  We may update this policy from time to time. The effective date at the top of the
                  page identifies the current version.
                </p>
              </section>

              <section className={styles.section} id="contact">
                <h2>How to contact us</h2>
                <p>
                  For pricing, cancellation, refund, or billing questions, email{' '}
                  <a className={styles.link} href="mailto:billing@innomightlabs.com">
                    billing@innomightlabs.com
                  </a>
                  . Include your account email and relevant charge or invoice details, but do not
                  send complete card numbers or security codes.
                </p>
              </section>
            </article>
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}
