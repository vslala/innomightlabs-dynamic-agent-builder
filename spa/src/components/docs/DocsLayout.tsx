import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Navbar } from '../Navbar';
import { Footer } from '../Footer';
import styles from './DocsLayout.module.css';

interface NavItem {
  id: string;
  label: string;
  href: string;
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
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id);
          }
        });
      },
      {
        rootMargin: '-100px 0px -60% 0px',
        threshold: 0,
      }
    );

    navItems.forEach((item) => {
      const element = document.getElementById(item.id);
      if (element) observer.observe(element);
    });

    return () => observer.disconnect();
  }, [navItems]);

  const docsNavLinks = [
    { path: '/docs/quick-start', label: 'Quick Start' },
    { path: '/docs/faq', label: 'FAQ' },
  ];

  return (
    <>
      <Navbar />
      <div className={styles.wrapper}>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarContent}>
            <div className={styles.docsNav}>
              <span className={styles.docsNavLabel}>Documentation</span>
              {docsNavLinks.map((link) => (
                <Link
                  key={link.path}
                  to={link.path}
                  className={`${styles.docsNavLink} ${location.pathname === link.path ? styles.docsNavLinkActive : ''}`}
                >
                  {link.label}
                </Link>
              ))}
            </div>

            <div className={styles.sectionNav}>
              <span className={styles.sectionNavLabel}>On this page</span>
              {navItems.map((item) => (
                <a
                  key={item.id}
                  href={item.href}
                  className={`${styles.navLink} ${activeSection === item.id ? styles.navLinkActive : ''}`}
                >
                  {item.label}
                </a>
              ))}
            </div>
          </div>
        </aside>

        <main className={styles.main}>
          <header className={styles.header}>
            <h1 className={styles.title}>{title}</h1>
            <p className={styles.description}>{description}</p>
          </header>
          <div className={styles.content}>{children}</div>
        </main>
      </div>
      <Footer />
    </>
  );
}
