import styles from './Hero.module.css';

export function Hero() {
  return (
    <section className={styles.hero}>
      <div className={styles.backgroundOrbs}>
        <div className={`${styles.orb} ${styles.orb1}`} />
        <div className={`${styles.orb} ${styles.orb2}`} />
        <div className={`${styles.orb} ${styles.orb3}`} />
      </div>

      <div className={styles.content}>
        <div className={styles.badge}>
          <span className={styles.badgeDot} />
          Coming Soon
        </div>

        <h1 className={styles.title}>
          Build <span className="gradient-text">Dynamic Agents</span>
          <br />
          with Long Term Memory
        </h1>

        <p className={styles.subtitle}>
          Create intelligent AI agents that remember, learn, and evolve.
          Our platform enables you to build agents with persistent memory,
          custom tools, and seamless integrations.
        </p>

        <div className={styles.cta}>
          <a href="/pricing" className={styles.primaryBtn}>
            Start Free
          </a>
          <a href="#features" className={styles.secondaryBtn}>
            Learn More
          </a>
        </div>

        <div className={styles.stats}>
          <div className={styles.stat}>
            <span className={styles.statNumber}>10x</span>
            <span className={styles.statLabel}>Faster Development</span>
          </div>
          <div className={styles.statDivider} />
          <div className={styles.stat}>
            <span className={styles.statNumber}>100%</span>
            <span className={styles.statLabel}>Customizable</span>
          </div>
          <div className={styles.statDivider} />
          <div className={styles.stat}>
            <span className={styles.statNumber}>Infinite</span>
            <span className={styles.statLabel}>Memory</span>
          </div>
        </div>
      </div>
    </section>
  );
}
