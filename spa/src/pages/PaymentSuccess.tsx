import { Navbar } from '../components/Navbar';
import { Footer } from '../components/Footer';
import styles from './PaymentResult.module.css';

export function PaymentSuccess() {
  return (
    <>
      <Navbar />
      <main className={styles.page}>
        <div className={styles.card}>
          <h1 className={styles.title}>
            Payment <span className="gradient-text">successful</span>
          </h1>
          <p className={styles.subtitle}>
            Thanks for subscribing. You will receive a confirmation email shortly.
          </p>
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
