import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, Bot, Globe, Magnet, Plug, ShieldCheck, Sparkles, Zap, type LucideIcon } from 'lucide-react';
import { Navbar } from '../components/Navbar';
import { Footer } from '../components/Footer';
import { pricingService } from '../services/pricing';
import { authService } from '../services/auth';
import { HttpError } from '../services/http';
import type { PricingResponse } from '../types/pricing';
import { Button } from '../components/ui/button';
import styles from './Pricing.module.css';
import { savePendingCheckout } from './pendingCheckout';
import { LIMIT_ROWS, formatLimit, includesLine, isCustom, isFree } from './pricingPlans';

type BillingCycle = 'monthly' | 'annual';

/** What every plan includes: plans differ in capacity and support, never in features. */
const INCLUDED: ReadonlyArray<readonly [LucideIcon, string, string]> = [
  [Sparkles, 'Ila, your solution builder', 'Describe the problem. Ila plans the solution, you approve it, she builds it.'],
  [Bot, 'Agents that know your business', 'Answers from your own content, with a link to the source, and a memory of each customer.'],
  [BookOpen, 'Knowledge from your site and files', 'Learns your website, PDFs and Office files, and re-reads them so answers stay current.'],
  [Magnet, 'Leads captured in conversation', 'One easy question at a time, with consent, saved the moment the lead is complete.'],
  [Zap, 'Automations that do the follow-up', 'On a schedule, on a new lead or on demand, with IF / ELSE, tests and a record of every run.'],
  [Globe, 'Everywhere your customers are', 'A chat widget in one snippet, a public API, agent-to-agent and a WordPress plugin.'],
  [Plug, 'Your existing tools', 'Gmail, Google Drive, Slack, HubSpot, Stripe, Notion, LinkedIn and more.'],
  [ShieldCheck, 'Safe by design', 'Nothing changes without your yes, every build can be undone, and secrets stay in a vault.'],
];

export function Pricing() {
  const navigate = useNavigate();
  const [billingCycle, setBillingCycle] = useState<BillingCycle>('monthly');
  const [pricing, setPricing] = useState<PricingResponse | null>(null);
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [activeCheckout, setActiveCheckout] = useState<string | null>(null);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const loadPricing = async () => {
      try {
        setStatus('loading');
        const response = await pricingService.getPricing();
        if (!active) {
          return;
        }
        setPricing(response);
        setStatus('success');
      } catch {
        if (!active) {
          return;
        }
        setStatus('error');
      }
    };

    loadPricing();

    return () => {
      active = false;
    };
  }, []);

  // The API decides whether a checkout is allowed (same plan, downgrade) and says why when it isn't.
  const handleCheckout = async (planKey: string) => {
    const user = authService.getUserFromToken();
    if (!user) {
      savePendingCheckout(planKey, billingCycle);
      navigate('/login');
      return;
    }

    setActiveCheckout(planKey);
    setCheckoutError(null);
    try {
      const response = await pricingService.createCheckoutSession(planKey, billingCycle, user.email);
      window.location.assign(response.url);
    } catch (error: unknown) {
      setActiveCheckout(null);
      setCheckoutError(
        error instanceof HttpError && error.status === 400
          ? error.message
          : 'We could not start checkout. Please try again in a moment.'
      );
    }
  };

  const plans = pricing?.tiers.filter((tier) => !isCustom(tier)) ?? [];
  const customPlans = pricing?.tiers.filter(isCustom) ?? [];

  return (
    <>
      <Navbar />
      <main className={styles.page}>
        <section className={styles.hero}>
          <div className={styles.backgroundOrbs}>
            <div className={`${styles.orb} ${styles.orb1}`} />
            <div className={`${styles.orb} ${styles.orb2}`} />
            <div className={`${styles.orb} ${styles.orb3}`} />
          </div>

          <div className={styles.heroContent}>
            <span className={styles.tag}>Pricing</span>
            <h1 className={styles.title}>
              Every feature in every plan.
              <br />
              <span className="gradient-text">Pay for what you run.</span>
            </h1>
            <p className={styles.subtitle}>
              Ila, agents, knowledge, leads and automations are in every plan. Plans differ only in
              capacity and support, and your AI usage is billed by your own provider with no markup from us.
            </p>

            <div className={styles.billingToggle}>
              <Button
                type="button"
                variant="ghost"
                className={billingCycle === 'monthly' ? styles.toggleActive : styles.toggleButton}
                onClick={() => setBillingCycle('monthly')}
              >
                Monthly
              </Button>
              <Button
                type="button"
                variant="ghost"
                className={billingCycle === 'annual' ? styles.toggleActive : styles.toggleButton}
                onClick={() => setBillingCycle('annual')}
              >
                Annual <span className={styles.toggleBadge}>2 months free</span>
              </Button>
            </div>
          </div>
        </section>

        <section className={styles.tiersSection}>
          {status === 'loading' && (
            <div className={styles.stateNotice}>Loading plans...</div>
          )}
          {status === 'error' && (
            <div className={styles.stateNotice}>
              Pricing is temporarily unavailable. Please refresh to try again.
            </div>
          )}
          {checkoutError && (
            <div className={styles.stateNotice} role="alert">{checkoutError}</div>
          )}
          {pricing && (
            <div className={styles.tiersGrid}>
              {plans.map((tier, index) => {
                const price = tier.prices[billingCycle];
                const checkingOut = activeCheckout !== null && activeCheckout === tier.planKey;
                const includes = includesLine(plans, index);
                return (
                  <div
                    key={tier.name}
                    className={`${styles.tierCard} ${tier.highlighted ? styles.tierHighlighted : ''}`}
                    style={{ animationDelay: `${index * 0.1}s` }}
                  >
                    <div className={styles.tierHeader}>
                      <span className={tier.highlighted ? styles.tierBadgeHighlighted : styles.tierBadge}>{tier.badge}</span>
                      <h3 className={styles.tierName}>{tier.name}</h3>
                      <p className={styles.tierDescription}>{tier.description}</p>
                    </div>

                    <div className={styles.priceBlock}>
                      <div className={styles.priceLine}>
                        <span className={styles.price}>{price}</span>
                        <span className={styles.pricePeriod}>
                          {isFree(tier) ? 'forever' : billingCycle === 'monthly' ? '/ month' : '/ year'}
                        </span>
                      </div>
                      <span className={styles.priceNote}>
                        {isFree(tier)
                          ? 'A card on file keeps the platform safe. No fee.'
                          : billingCycle === 'monthly'
                            ? `or ${tier.prices.annual} a year, two months free`
                            : `${tier.prices.monthly} a month if paid monthly`}
                      </span>
                    </div>

                    {tier.planKey ? (
                      <Button
                        type="button"
                        variant="ghost"
                        className={tier.highlighted ? styles.tierCta : styles.tierCtaQuiet}
                        onClick={() => handleCheckout(tier.planKey as string)}
                        disabled={checkingOut}
                      >
                        {checkingOut ? 'Redirecting...' : tier.ctaLabel}
                      </Button>
                    ) : (
                      <a href={tier.ctaHref} className={tier.highlighted ? styles.tierCta : styles.tierCtaQuiet}>
                        {tier.ctaLabel}
                      </a>
                    )}

                    <div>
                      {includes && <p className={styles.includesLine}>{includes}</p>}
                      <ul className={styles.featureList}>
                        {tier.features.map((feature) => (
                          <li key={feature} className={styles.featureItem}>
                            {feature}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          {pricing && (
            <p className={styles.aiNote}>
              <b>Your AI, at cost.</b> Connect your own OpenAI, Anthropic, Google Gemini or AWS Bedrock
              account and pay your provider directly. We never mark up AI usage.
            </p>
          )}
        </section>

        <section className={styles.includedSection} aria-labelledby="included-title">
          <div className={styles.sectionHeader}>
            <span className={styles.tag}>In every plan</span>
            <h2 id="included-title" className={styles.sectionTitle}>
              Not a chatbot.
              <span className="gradient-text"> A team that does the work.</span>
            </h2>
            <p className={styles.sectionSubtitle}>
              Even the Free plan gets the whole platform. Upgrade when you need more of it.
            </p>
          </div>
          <div className={styles.includedGrid}>
            {INCLUDED.map(([Icon, title, body]) => (
              <article key={title} className={styles.includedItem}>
                <span className={styles.includedIcon}><Icon size={20} aria-hidden /></span>
                <h3>{title}</h3>
                <p>{body}</p>
              </article>
            ))}
          </div>
        </section>

        {pricing && (
          <section className={styles.compareSection} aria-labelledby="compare-title">
            <div className={styles.sectionHeader}>
              <span className={styles.tag}>Compare plans</span>
              <h2 id="compare-title" className={styles.sectionTitle}>How much each plan runs</h2>
            </div>
            <div className={styles.compareScroll}>
              <table className={styles.compareTable}>
                <thead>
                  <tr>
                    <th scope="col"><span className={styles.visuallyHidden}>Limit</span></th>
                    {pricing.tiers.map((tier) => (
                      <th key={tier.name} scope="col" className={tier.highlighted ? styles.compareHighlighted : undefined}>
                        {tier.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {LIMIT_ROWS.map(([limit, label]) => (
                    <tr key={limit}>
                      <th scope="row">{label}</th>
                      {pricing.tiers.map((tier) => (
                        <td key={tier.name} className={tier.highlighted ? styles.compareHighlighted : undefined}>
                          {isCustom(tier) ? 'Custom' : formatLimit(tier.limits[limit])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {pricing && (pricing.addons.length > 0 || customPlans.length > 0) && (
          <section className={styles.addOnsSection} aria-labelledby="help-title">
            <div className={styles.sectionHeader}>
              <span className={styles.tag}>Help when you want it</span>
              <h2 id="help-title" className={styles.sectionTitle}>
                We can build it
                <span className="gradient-text"> with you</span>
              </h2>
            </div>
            <div className={styles.addOnsGrid}>
              {pricing.addons.map((addon) => (
                <article key={addon.name} className={styles.addOnCard}>
                  <h3 className={styles.tierName}>{addon.name}</h3>
                  <p className={styles.addOnPrice}>
                    {addon.price} <span className={styles.pricePeriod}>{addon.period}</span>
                  </p>
                  <p className={styles.addOnDescription}>{addon.description}</p>
                  <ul className={styles.featureList}>
                    {addon.features.map((feature) => (
                      <li key={feature} className={styles.featureItem}>{feature}</li>
                    ))}
                  </ul>
                  <a href={addon.ctaHref} className={styles.tierCtaQuiet}>{addon.ctaLabel}</a>
                </article>
              ))}
              {customPlans.map((tier) => (
                <article key={tier.name} className={styles.addOnCard}>
                  <h3 className={styles.tierName}>{tier.name}</h3>
                  <p className={styles.addOnPrice}>Custom pricing</p>
                  <p className={styles.addOnDescription}>{tier.description}</p>
                  <ul className={styles.featureList}>
                    {tier.features.map((feature) => (
                      <li key={feature} className={styles.featureItem}>{feature}</li>
                    ))}
                  </ul>
                  <a href={tier.ctaHref} className={styles.tierCtaQuiet}>{tier.ctaLabel}</a>
                </article>
              ))}
            </div>
          </section>
        )}

        <section className={styles.policySummary} aria-labelledby="pricing-details-title">
          <div className={styles.policySummaryHeader}>
            <span className={styles.tag}>Billing details</span>
            <h2 id="pricing-details-title" className={styles.sectionTitle}>
              Clear terms before you subscribe
            </h2>
            <p className={styles.sectionSubtitle}>
              The plan, billing cycle, price, and any discount are shown again at checkout before
              you confirm your subscription.
            </p>
          </div>

          <div className={styles.policySummaryGrid}>
            <article className={styles.policySummaryItem}>
              <h3>Monthly or annual</h3>
              <p>
                Monthly plans renew monthly. Annual prices are charged for the full year and
                renew annually unless cancelled.
              </p>
            </article>
            <article className={styles.policySummaryItem}>
              <h3>No automatic overages</h3>
              <p>
                Usage is capped at the limits included with your plan. We prompt you to upgrade
                instead of automatically charging usage overages.
              </p>
            </article>
            <article className={styles.policySummaryItem}>
              <h3>Cancel from settings</h3>
              <p>
                Cancel before renewal to prevent the next charge. Paid access continues through
                the end of your current billing period.
              </p>
            </article>
            <article className={styles.policySummaryItem}>
              <h3>Secure payment processing</h3>
              <p>
                Stripe processes card payments. The Free plan requires a valid card for account
                verification and abuse prevention but has no subscription fee.
              </p>
            </article>
          </div>

          <p className={styles.policySummaryLink}>
            Read the full{' '}
            <a href="/legal/pricing">Pricing Policy</a>
            {' '}for plan changes, taxes, promotions, refunds, and billing errors.
          </p>
        </section>

        <section className={styles.faqSection}>
          <div className={styles.sectionHeader}>
            <span className={styles.tag}>FAQ</span>
            <h2 className={styles.sectionTitle}>
              Pricing questions,
              <span className="gradient-text"> answered</span>
            </h2>
          </div>
          {pricing && (
            <div className={styles.faqGrid}>
              {pricing.faqs.map((item) => (
                <div key={item.question} className={styles.faqCard}>
                  <h3>{item.question}</h3>
                  <p>{item.answer}</p>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className={styles.ctaSection}>
          <div className={styles.ctaContent}>
            <h2>Put AI to work on your business today</h2>
            <p>Start free, tell Ila what you need, and upgrade when it is earning its keep.</p>
            <Button
              type="button"
              variant="ghost"
              className={styles.ctaButton}
              onClick={() => handleCheckout('free')}
              disabled={activeCheckout === 'free'}
            >
              {activeCheckout === 'free' ? 'Redirecting...' : 'Start free'}
            </Button>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
