import { Link } from 'react-router-dom';
import { FEATURES } from '../routes/features';
import styles from './Footer.module.css';

export function Footer() {
  return <footer className={styles.footer}>
    <nav className={styles.container} aria-label="Footer navigation">
      <Link to="/">Home</Link>
      {FEATURES.map(feature => <Link key={feature.path} to={feature.path}>{feature.title}</Link>)}
      <Link to="/pricing">Pricing</Link>
      <Link to="/docs/quick-start">Docs</Link>
      <Link to="/whats-new">What's New</Link>
      <Link to="/legal/privacy">Privacy Policy</Link>
      <Link to="/legal/pricing">Pricing Policy</Link>
      <Link to="/legal/terms">Terms of Service</Link>
      <Link to="/sitemap">Sitemap</Link>
      <span>© {new Date().getFullYear()} InnomightLabs</span>
    </nav>
  </footer>;
}
