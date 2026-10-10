import { Cpu, ShieldCheck, Undo2 } from 'lucide-react';
import { IlaDemo } from './landing/IlaDemo';
import styles from './Hero.module.css';

const promises = [
  { icon: ShieldCheck, text: 'You approve every plan' },
  { icon: Undo2, text: 'Roll back any version' },
  { icon: Cpu, text: 'Runs on your own model provider' },
];

export function Hero() {
  return (
    <section className={styles.hero}>
      <div className={styles.backgroundOrbs}>
        <div className={`${styles.orb} ${styles.orb1}`} />
        <div className={`${styles.orb} ${styles.orb2}`} />
        <div className={`${styles.orb} ${styles.orb3}`} />
      </div>

      <div className={styles.layout}>
        <div className={styles.content}>
          <div className={styles.badge}>
            <span className={styles.badgeDot} />
            Meet Ila, your solution builder
          </div>

          <h1 className={styles.title}>
            Tell Ila what you need.
            <br />
            <span className="gradient-text">She builds it, you ship it.</span>
          </h1>

          <p className={styles.subtitle}>
            InnomightLabs is one place to build and deliver AI solutions: assistants that know your business, chat
            widgets for your website, and agents that do the work. Describe the outcome, approve Ila's plan, and
            everything she builds arrives as one kit you can change or roll back.
          </p>

          <div className={styles.cta}>
            <a href="/pricing" className={styles.primaryBtn}>
              Start building free
            </a>
            <a href="#how-it-works" className={styles.secondaryBtn}>
              See how it works
            </a>
          </div>

          <ul className={styles.promises}>
            {promises.map(({ icon: Icon, text }) => (
              <li key={text}>
                <Icon aria-hidden="true" />
                {text}
              </li>
            ))}
          </ul>
        </div>

        <div className={styles.demo}>
          <IlaDemo />
        </div>
      </div>
    </section>
  );
}
