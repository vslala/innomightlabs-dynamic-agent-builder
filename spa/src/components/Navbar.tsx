import { useState, useEffect } from 'react';
import styles from './Navbar.module.css';

export function Navbar() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 50);
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <nav className={`${styles.navbar} ${scrolled ? styles.scrolled : ''}`}>
      <div className={styles.container}>
        <a href="#" className={styles.logo}>
          InnoMight Labs
        </a>

        <div className={styles.links}>
          <a href="#features" className={styles.link}>Features</a>
          <a href="#how-it-works" className={styles.link}>How It Works</a>
          <a href="#waitlist" className={styles.ctaLink}>Join Waitlist</a>
        </div>
      </div>
    </nav>
  );
}
