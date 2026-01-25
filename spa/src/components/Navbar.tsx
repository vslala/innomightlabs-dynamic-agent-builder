import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { authService } from '../services/auth';
import styles from './Navbar.module.css';

export function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const location = useLocation();
  const isDocsPage = location.pathname.startsWith('/docs');
  const isAuthenticated = authService.isAuthenticated();

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 50);
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <nav className={`${styles.navbar} ${scrolled || isDocsPage ? styles.scrolled : ''}`}>
      <div className={styles.container}>
        <Link to="/" className={styles.logo}>
          InnoMight Labs
        </Link>

        <div className={styles.links}>
          <a href={`${import.meta.env.BASE_URL}#features`} className={styles.link}>Features</a>
          <a href={`${import.meta.env.BASE_URL}#how-it-works`} className={styles.link}>How It Works</a>
          <Link to="/pricing" className={styles.link}>Pricing</Link>
          <Link to="/docs/quick-start" className={styles.link}>Docs</Link>
          <Link to="/contact" className={styles.link}>Contact</Link>
          {isAuthenticated ? (
            <Link to="/dashboard" className={styles.ctaLink}>Dashboard</Link>
          ) : (
            <Link to="/login" className={styles.ctaLink}>Login</Link>
          )}
        </div>
      </div>
    </nav>
  );
}
