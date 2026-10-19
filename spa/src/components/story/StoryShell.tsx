import { useEffect, useRef, type ReactNode } from 'react';
import { ArrowLeft, ArrowRight, BookOpen, Bot, CalendarDays, Check, ChevronRight, Clock, Code, DollarSign, Eye, FileText, Flag, GitBranch, Globe, Inbox, KeyRound, Layers, Link, Lock, Mail, Menu, MessageSquare, Play, Plug, Plus, Search, Send, Shield, Sparkles, Star, Undo2, User, Users, X, Zap, TriangleAlert, Command, type LucideIcon } from 'lucide-react';
import { Navbar } from '../Navbar';
import { Footer } from '../Footer';
import styles from './StoryPage.module.css';

const icons: Record<string, LucideIcon> = {
  arrow: ArrowLeft, right: ChevronRight, clock: Clock, mail: Mail, bot: Bot, file: FileText,
  search: Search, plug: Plug, branch: GitBranch, cal: CalendarDays, zap: Zap, flag: Flag,
  play: Play, check: Check, x: X, user: User, users: Users, sparkles: Sparkles,
  msg: MessageSquare, globe: Globe, book: BookOpen, plus: Plus, star: Star, lock: Lock,
  key: KeyRound, code: Code, link: Link, shield: Shield, layers: Layers, undo: Undo2,
  send: Send, eye: Eye, dollar: DollarSign, menu: Menu, cmd: Command, inbox: Inbox,
  alert: TriangleAlert, 'arrow-right': ArrowRight,
};

export function StoryIcon({ name }: { name: string }) {
  const Icon = icons[name] ?? Sparkles;
  return <Icon aria-hidden="true" focusable="false" />;
}

export function StoryPage({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const progress = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = title.includes('InnomightLabs') ? title : `${title} | InnomightLabs`;
    const meta = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    const previousDescription = meta?.content;
    if (meta && description) meta.content = description;
    return () => {
      document.title = previousTitle;
      if (meta && previousDescription !== undefined) meta.content = previousDescription;
    };
  }, [title, description]);

  useEffect(() => {
    const elements = root.current?.querySelectorAll(`.${styles.rv}`) ?? [];
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced || !('IntersectionObserver' in window)) {
      elements.forEach(element => element.classList.add(styles.in));
      return;
    }
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add(styles.in);
        entry.target.dispatchEvent(new Event('seen'));
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.15 });
    elements.forEach(element => observer.observe(element));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const update = () => {
      const distance = document.documentElement.scrollHeight - window.innerHeight;
      if (progress.current) progress.current.style.width = `${distance > 0 ? Math.min(100, Math.max(0, window.scrollY / distance * 100)) : 0}%`;
    };
    update();
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, []);

  return <div ref={root} className={styles.story}>
    <div ref={progress} className={styles.progress} aria-hidden="true" />
    <Navbar />
    <main className={styles.content}>{children}</main>
    <Footer />
  </div>;
}
