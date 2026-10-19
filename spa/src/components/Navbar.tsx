import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { ChevronDown, Menu, X } from 'lucide-react';
import { authService } from '../services/auth';
import { FEATURES } from '../routes/features';
import logo from '../assets/brand/innomightlabs-logo.png';
import styles from './Navbar.module.css';

export function Navbar() {
  const [featuresOpen, setFeaturesOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const root = useRef<HTMLElement>(null);
  const featureButton = useRef<HTMLButtonElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const location = useLocation();
  const isAuthenticated = authService.isAuthenticated();
  const close = () => { setFeaturesOpen(false); setMobileOpen(false); };

  useEffect(() => {
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) close();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (featuresOpen) { setFeaturesOpen(false); featureButton.current?.focus(); }
      else if (mobileOpen) { setMobileOpen(false); menuButton.current?.focus(); }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [featuresOpen, mobileOpen]);

  const navClass = ({ isActive }: { isActive: boolean }) => `${styles.link} ${isActive ? styles.active : ''}`;
  return <nav ref={root} className={styles.navbar} aria-label="Main navigation" onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget)) close();
  }}>
    <div className={styles.container}>
      <Link to="/" className={styles.logo} aria-label="InnomightLabs home" onClick={close}>
        <img className={styles.logoMark} src={logo} alt="" />
        <span className={styles.logoText}>InnomightLabs</span>
      </Link>
      <button ref={menuButton} type="button" className={styles.menuButton} aria-label={mobileOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={mobileOpen} aria-controls="public-navigation" onClick={() => { setMobileOpen(open => !open); setFeaturesOpen(false); }}>
        {mobileOpen ? <X size={22} /> : <Menu size={22} />}
      </button>
      <div id="public-navigation" className={`${styles.links} ${mobileOpen ? styles.open : ''}`}>
        <div className={styles.features}>
          <button ref={featureButton} type="button" className={`${styles.link} ${location.pathname.startsWith('/features/') ? styles.active : ''}`} aria-expanded={featuresOpen} aria-controls="feature-navigation" onClick={() => setFeaturesOpen(open => !open)}>
            Features <ChevronDown size={14} className={featuresOpen ? styles.chevronOpen : ''} />
          </button>
          {featuresOpen && <div id="feature-navigation" className={styles.dropdown}>
            {FEATURES.map(feature => <NavLink key={feature.path} to={feature.path} className={navClass} onClick={close}><span>{feature.title}<small>{feature.description}</small></span></NavLink>)}
          </div>}
        </div>
        <NavLink to="/pricing" className={navClass} onClick={close}>Pricing</NavLink>
        <NavLink to="/downloads" className={navClass} onClick={close}>Downloads</NavLink>
        <NavLink to="/docs/quick-start" className={navClass} onClick={close}>Docs</NavLink>
        <NavLink to="/contact" className={navClass} onClick={close}>Contact</NavLink>
        <Link to={isAuthenticated ? '/dashboard' : '/login'} className={styles.ctaLink} onClick={close}>{isAuthenticated ? 'Dashboard' : 'Try it free'}</Link>
      </div>
    </div>
  </nav>;
}
