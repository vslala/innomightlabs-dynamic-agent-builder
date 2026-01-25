import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Navbar } from '../components/Navbar';
import { Footer } from '../components/Footer';
import { pricingService } from '../services/pricing';
import { authService } from '../services/auth';
import { httpClient } from '../services/http';
import type { PricingResponse } from '../types/pricing';
import styles from './Pricing.module.css';

type BillingCycle = 'monthly' | 'annual';

type SubscriptionStatus = {
  tier: string;
  status?: string | null;
  current_period_start?: string | null;
  current_period_end?: string | null;
  is_active: boolean;
};

export function Pricing() {
  const navigate = useNavigate();
  const [billingCycle, setBillingCycle] = useState<BillingCycle>('monthly');
  const [pricing, setPricing] = useState<PricingResponse | null>(null);
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [checkoutStatus, setCheckoutStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const [activeCheckout, setActiveCheckout] = useState<string | null>(null);

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

  const handleCheckout = async (planKey: string) => {
    try {
      setCheckoutStatus('loading');
      setActiveCheckout(planKey);

      // Check if user is authenticated
      const user = authService.getUserFromToken();
      if (!user) {
        // Store checkout intent so we can complete it after login
        sessionStorage.setItem('pendingCheckout', JSON.stringify({
          planKey,
          billingCycle,
          timestamp: Date.now()
        }));

        // Redirect to login page where user can choose between Google or Email
        navigate('/login');
        return;
      }

      // Fetch current subscription to validate
      try {
        const currentSub = await httpClient.get<SubscriptionStatus>(
          '/payments/stripe/subscription/status'
        );

        // Client-side validation for better UX
        if (currentSub.is_active) {
          const currentTier = currentSub.tier || 'free';

          // Check for duplicate plan
          if (currentTier === planKey) {
            alert(
              `You already have an active ${planKey} plan.\n` +
              `Visit Settings to manage your subscription.`
            );
            setCheckoutStatus('idle');
            setActiveCheckout(null);
            return;
          }

          // Check for downgrade attempt
          const tierOrder: Record<string, number> = {
            free: 0, starter: 1, pro: 2, enterprise: 3
          };
          if (tierOrder[planKey] < tierOrder[currentTier]) {
            alert(
              `To downgrade from ${currentTier} to ${planKey}, ` +
              `please visit Settings → Manage Subscription.`
            );
            setCheckoutStatus('idle');
            setActiveCheckout(null);
            return;
          }
        }
      } catch (error) {
        // No subscription or error fetching - proceed with checkout
        console.log('No active subscription found, proceeding with checkout');
      }

      // Proceed with checkout
      const response = await pricingService.createCheckoutSession(
        planKey,
        billingCycle,
        user.email
      );

      window.location.href = response.url;
    } catch (error: unknown) {
      setCheckoutStatus('error');
      setActiveCheckout(null);

      // Show backend error message if available
      if (error && typeof error === 'object' && 'response' in error) {
        const httpError = error as { response?: { data?: { detail?: string } } };
        if (httpError.response?.data?.detail) {
          alert(httpError.response.data.detail);
        } else {
          alert('Failed to start checkout. Please try again.');
        }
      } else {
        alert('Failed to start checkout. Please try again.');
      }
    }
  };

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
              Flexible plans for
              <br />
              <span className="gradient-text">memory-first agents</span>
            </h1>
            <p className={styles.subtitle}>
              Start free, then scale with higher limits as your agents grow.
              Annual billing saves 17% across paid plans.
            </p>

            <div className={styles.billingToggle}>
              <button
                type="button"
                className={billingCycle === 'monthly' ? styles.toggleActive : styles.toggleButton}
                onClick={() => setBillingCycle('monthly')}
              >
                Monthly
              </button>
              <button
                type="button"
                className={billingCycle === 'annual' ? styles.toggleActive : styles.toggleButton}
                onClick={() => setBillingCycle('annual')}
              >
                Annual <span className={styles.toggleBadge}>Save 17%</span>
              </button>
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
          {pricing && (
            <div className={styles.tiersGrid}>
              {pricing.tiers.map((tier, index) => {
                const price = tier.prices[billingCycle];
                const canCheckout = Boolean(tier.planKey && price !== 'Custom');
                return (
                  <div
                    key={tier.name}
                    className={`${styles.tierCard} ${tier.highlighted ? styles.tierHighlighted : ''}`}
                    style={{ animationDelay: `${index * 0.1}s` }}
                  >
                    <div className={styles.tierHeader}>
                      <span className={styles.tierBadge}>{tier.badge}</span>
                      <h3 className={styles.tierName}>{tier.name}</h3>
                      <p className={styles.tierDescription}>{tier.description}</p>
                    </div>

                    <div className={styles.priceBlock}>
                      <span className={styles.price}>{price}</span>
                      <span className={styles.pricePeriod}>
                        {price === 'Custom' ? "Let's talk" : `per ${billingCycle === 'monthly' ? 'month' : 'year'}`}
                      </span>
                    </div>
                    {tier.planKey === 'free' && (
                      <p className={styles.tierNote}>
                        Free plan with a required card on file to protect the platform.
                      </p>
                    )}

                    {canCheckout ? (
                      <button
                        type="button"
                        className={styles.tierCta}
                        onClick={() => handleCheckout(tier.planKey as string)}
                        disabled={checkoutStatus === 'loading' && activeCheckout === tier.planKey}
                      >
                        {checkoutStatus === 'loading' && activeCheckout === tier.planKey
                          ? 'Redirecting...'
                          : tier.ctaLabel}
                      </button>
                    ) : (
                      <a href={tier.ctaHref} className={styles.tierCta}>
                        {tier.ctaLabel}
                      </a>
                    )}

                    <ul className={styles.featureList}>
                      {tier.features.map((feature) => (
                        <li key={feature} className={styles.featureItem}>
                          {feature}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          )}
          {checkoutStatus === 'error' && (
            <div className={styles.stateNotice}>
              Unable to start checkout. Please try again in a moment.
            </div>
          )}
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
            <h2>Ready to build agents with long-term memory?</h2>
            <p>Start free today with a card on file, then upgrade when you need more capacity.</p>
            <button
              type="button"
              className={styles.ctaButton}
              onClick={() => handleCheckout('free')}
              disabled={checkoutStatus === 'loading' && activeCheckout === 'free'}
            >
              {checkoutStatus === 'loading' && activeCheckout === 'free'
                ? 'Redirecting...'
                : 'Start Free'}
            </button>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
