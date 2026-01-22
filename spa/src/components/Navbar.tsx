import { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { authService } from '../services/auth';
import styles from './Navbar.module.css';

export function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const location = useLocation();
  const isDocsPage = location.pathname.startsWith('/docs');
  const isLandingPage = location.pathname === '/';
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
          {isLandingPage && (
            <>
              <a href="#features" className={styles.link}>Features</a>
              <a href="#how-it-works" className={styles.link}>How It Works</a>
            </>
          )}
          <Link to="/pricing" className={styles.link}>Pricing</Link>
          <Link to="/docs/quick-start" className={styles.link}>Docs</Link>
          {isAuthenticated ? (
            <Link to="/dashboard" className={styles.ctaLink}>Dashboard</Link>
          ) : (
            <>
              <a
                href={`${import.meta.env.VITE_API_BASE_URL}/auth/cognito`}
                className={styles.link}
              >
                Email Login
              </a>
              <a
                href={`${import.meta.env.VITE_API_BASE_URL}/auth/google`}
                className={styles.betaLogin}
              >
                Beta Login
              </a>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
