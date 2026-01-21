import { Navbar } from '../components/Navbar';
import { Footer } from '../components/Footer';
import styles from './PaymentResult.module.css';

export function PaymentCancel() {
  return (
    <>
      <Navbar />
      <main className={styles.page}>
        <div className={styles.card}>
          <h1 className={styles.title}>
            Checkout <span className="gradient-text">canceled</span>
          </h1>
          <p className={styles.subtitle}>
            No charges were made. You can return to pricing whenever you are ready.
          </p>
          <div className={styles.actions}>
            <a href="/pricing" className={styles.primary}>
              Back to Pricing
            </a>
            <a href="/#waitlist" className={styles.secondary}>
              Join the Waitlist
            </a>
          </div>
        </div>
      </main>
      <Footer />
    </>
  );
}
