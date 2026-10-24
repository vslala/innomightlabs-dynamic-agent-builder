import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Navbar } from '../Navbar';
import { Footer } from '../Footer';
import styles from './DocsLayout.module.css';

interface NavItem {
  id: string;
  label: string;
  href: string;
  nested?: boolean;
}

interface DocsLayoutProps {
  children: React.ReactNode;
  navItems: NavItem[];
  title: string;
  description: string;
}

export function DocsLayout({ children, navItems, title, description }: DocsLayoutProps) {
  const [activeSection, setActiveSection] = useState<string>(navItems[0]?.id || '');
  const location = useLocation();

  useEffect(() => {
    const sections = navItems.flatMap((item) => {
      const element = document.getElementById(item.id);
      return element ? [element] : [];
    });
    let frame: number | null = null;

    const updateActiveSection = () => {
      frame = null;
      // Use heading positions, not intersection order: nested sections can overlap.
      const current = sections.filter((section) => section.getBoundingClientRect().top <= 120).at(-1);
      setActiveSection(current?.id ?? sections[0]?.id ?? '');
    };
    const scheduleUpdate = () => {
      if (frame === null) frame = window.requestAnimationFrame(updateActiveSection);
    };

    scheduleUpdate();
    window.addEventListener('scroll', scheduleUpdate, { passive: true });
    window.addEventListener('resize', scheduleUpdate);
    return () => {
      if (frame !== null) window.cancelAnimationFrame(frame);
      window.removeEventListener('scroll', scheduleUpdate);
      window.removeEventListener('resize', scheduleUpdate);
    };
  }, [navItems, location.pathname]);

  const docsNavLinks = [
    { path: '/docs/quick-start', label: 'Quick Start' },
    { path: '/docs/automations', label: 'Automations' },
    { path: '/docs/agent-to-agent', label: 'Agent2Agent' },
    { path: '/docs/public-api', label: 'Public API' },
    { path: '/docs/faq', label: 'FAQ' },
    { path: '/whats-new', label: "What's New" },
  ];

  const sectionLinks = navItems.map((item) => (
    <a
      key={item.id}
      href={item.href}
      aria-current={activeSection === item.id ? 'location' : undefined}
      className={`${styles.navLink} ${item.nested ? styles.navLinkNested : ''} ${activeSection === item.id ? styles.navLinkActive : ''}`}
    >
      {item.label}
    </a>
  ));

  return (
    <>
      <Navbar />
      <div className={styles.wrapper}>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarContent}>
            <nav className={styles.docsNav} aria-label="Documentation">
              <span className={styles.docsNavLabel}>Documentation</span>
              {docsNavLinks.map((link) => (
                <Link
                  key={link.path}
                  to={link.path}
                  aria-current={location.pathname === link.path ? 'page' : undefined}
                  className={`${styles.docsNavLink} ${location.pathname === link.path ? styles.docsNavLinkActive : ''}`}
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          </div>
        </aside>

        <main className={styles.main}>
          <header className={styles.header}>
            <h1 className={styles.title}>{title}</h1>
            <p className={styles.description}>{description}</p>
          </header>
          {navItems.length > 0 && (
            <details className={styles.mobileIndex}>
              <summary>On this page</summary>
              <nav className={styles.sectionNav} aria-label="On this page">
                {sectionLinks}
              </nav>
            </details>
          )}
          <div className={styles.content}>{children}</div>
        </main>

        {navItems.length > 0 && (
          <aside className={styles.pageIndex}>
            <nav className={styles.sectionNav} aria-label="On this page">
              <span className={styles.sectionNavLabel}>On this page</span>
              {sectionLinks}
            </nav>
          </aside>
        )}
      </div>
      <Footer />
    </>
  );
}
