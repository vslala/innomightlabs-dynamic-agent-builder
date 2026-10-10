import logo from '../assets/brand/innomightlabs-logo.png';
import styles from './Footer.module.css';

export function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer className={styles.footer}>
      <div className={styles.container}>
        <div className={styles.brand}>
          <div className={styles.brandRow}>
            <img
              className={styles.logoMark}
              src={logo}
              alt="InnoMight Labs logo"
            />
            <span className={styles.logo}>InnoMight Labs</span>
          </div>
          <p className={styles.tagline}>One place to build and deliver AI solutions.</p>
        </div>

        <div className={styles.divider} />

        <div className={styles.bottom}>
          <p className={styles.copyright}>
            {currentYear} InnoMight Labs. All rights reserved.
          </p>
          <div className={styles.links}>
            <a href="/whats-new" className={styles.link}>What's New</a>
            <a href="/legal/privacy" className={styles.link}>Privacy Policy</a>
            <a href="/legal/pricing" className={styles.link}>Pricing Policy</a>
            <a href="/legal/terms" className={styles.link}>Terms of Service</a>
            <a href="/sitemap" className={styles.link}>Sitemap</a>
          </div>
        </div>
      </div>
    </footer>
  );
}
