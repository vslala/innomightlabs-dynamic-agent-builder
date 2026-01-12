import { useState, type FormEvent } from 'react';
import { subscriptionService } from '../services/subscription';
import styles from './WaitlistForm.module.css';

export function WaitlistForm() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    if (!email.trim()) {
      setStatus('error');
      setMessage('Please enter your email address.');
      return;
    }

    setStatus('loading');
    setMessage('');

    try {
      const result = await subscriptionService.subscribe(email);

      if (result.success) {
        setStatus('success');
        setMessage(result.message);
        setEmail('');
      } else {
        setStatus('error');
        setMessage(result.message);
      }
    } catch {
      setStatus('error');
      setMessage('Something went wrong. Please try again.');
    }
  };

  return (
    <section id="waitlist" className={styles.waitlist}>
      <div className={styles.container}>
        <div className={styles.card}>
          <div className={styles.cardContent}>
            <span className={styles.tag}>Join the Waitlist</span>
            <h2 className={styles.title}>
              Be the first to build
              <br />
              <span className="gradient-text">intelligent agents</span>
            </h2>
            <p className={styles.subtitle}>
              Get early access to our platform and start building AI agents with
              long-term memory before anyone else.
            </p>

            <form onSubmit={handleSubmit} className={styles.form}>
              <div className={styles.inputWrapper}>
                <input
                  type="email"
                  placeholder="Enter your email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className={styles.input}
                  disabled={status === 'loading'}
                />
                <button
                  type="submit"
                  className={styles.submitBtn}
                  disabled={status === 'loading'}
                >
                  {status === 'loading' ? (
                    <span className={styles.spinner} />
                  ) : (
                    'Get Early Access'
                  )}
                </button>
              </div>

              {message && (
                <p
                  className={`${styles.message} ${
                    status === 'success' ? styles.success : styles.error
                  }`}
                >
                  {message}
                </p>
              )}
            </form>

            <p className={styles.privacy}>
              We respect your privacy. Unsubscribe at any time.
            </p>
          </div>

          <div className={styles.decoration}>
            <div className={styles.decorOrb1} />
            <div className={styles.decorOrb2} />
          </div>
        </div>
      </div>
    </section>
  );
}
