import { useEffect, useState } from 'react';
import { Navbar } from '../components/Navbar';
import { Footer } from '../components/Footer';
import { httpClient } from '../services/http';
import { authService } from '../services/auth';
import styles from './PaymentResult.module.css';

type SessionAuthResponse = {
  token: string;
  email: string;
  subscription_status?: string | null;
};

type SubscriptionStatusResponse = {
  tier: string;
  status?: string | null;
  current_period_end?: string | null;
  is_active: boolean;
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function PaymentSuccess() {
  const [status, setStatus] = useState('Confirming payment...');
  const [email, setEmail] = useState<string | null>(null);
  const [tier, setTier] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get('session_id');

    if (!sessionId) {
      setError('Missing checkout session. Please contact support.');
      return () => {
        active = false;
      };
    }

    const pollSubscription = async () => {
      for (let attempt = 0; attempt < 8; attempt += 1) {
        const subscription = await httpClient.get<SubscriptionStatusResponse>(
          '/payments/stripe/subscription/status'
        );
        if (subscription.is_active) {
          return subscription;
        }
        await sleep(1500);
      }
      return null;
    };

    const confirmPayment = async () => {
      try {
        const session = await httpClient.get<SessionAuthResponse>(
          `/payments/stripe/session/${sessionId}`,
          { skipAuth: true }
        );
        if (!active) {
          return;
        }
        authService.setToken(session.token);
        setEmail(session.email);
        setStatus('Syncing your subscription...');

        const subscription = await pollSubscription();
        if (!active) {
          return;
        }
        if (subscription) {
          setTier(subscription.tier);
          setStatus('Subscription activated.');
        } else {
          setStatus('Payment confirmed. Subscription will appear shortly.');
        }
      } catch {
        if (!active) {
          return;
        }
        setError('We could not confirm the payment. Please try again.');
      }
    };

    confirmPayment();

    return () => {
      active = false;
    };
  }, []);

  return (
    <>
      <Navbar />
      <main className={styles.page}>
        <div className={styles.card}>
          <h1 className={styles.title}>
            Payment <span className="gradient-text">successful</span>
          </h1>
          {error ? (
            <p className={styles.subtitle}>{error}</p>
          ) : (
            <p className={styles.subtitle}>
              {status}
              {tier ? ` You are now on the ${tier} plan.` : ''}
              {email ? ` Signed in as ${email}.` : ''}
            </p>
          )}
          <div className={styles.actions}>
            <a href="/dashboard" className={styles.primary}>
              Go to Dashboard
            </a>
            <a href="/pricing" className={styles.secondary}>
              Back to Pricing
            </a>
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}
