import { Link } from 'react-router-dom';
import { StoryIcon, StoryPage, storyClasses } from '../components/story/StoryPage';
import { HomeAgents, HomeGoals, HomeHeroDemo, HomeJourney, HomeLeadsDemo, HomeNightDemo } from './homeDemos';
import styles from './LandingPage.module.css';

const cx = storyClasses(styles);
const PARTS = [
  ['book', 'Knowledge from your site'], ['zap', 'Skills: email, Drive, forms'],
  ['plug', 'Connectors for your tools'], ['star', 'Memory across chats'],
  ['globe', 'Chat widget for your site'], ['code', 'Public API'],
  ['users', 'Share with your team'], ['layers', 'Kits you can undo'],
] as const;
const FEATURES = [
  ['ila', 'sparkles', 'Ila', 'Build by talking'], ['agents', 'bot', 'Agents', 'Your AI team'],
  ['leads', 'inbox', 'Leads', 'Customers, captured'], ['automations', 'clock', 'Automations', 'Work while you sleep'],
] as const;

export function LandingPage() {
  return <StoryPage title="Build your AI team by talking to it | InnomightLabs" description="Describe what your business needs. Ila plans it, you approve it, and agents, leads and automations start working for you.">
    <header className={cx('hero')}><div className={cx('wrap')}><div className={cx('intro')}>
      <span className={cx('eyebrow')}>Meet Ila, your solution builder</span>
      <h1>Build your AI team<br /><span className={cx('grad')}>by talking to it.</span></h1>
      <p className={cx('lead')}>Describe what your business needs. Ila plans it, you approve it, and agents, leads and automations start working for you. No code, and nothing changes without your yes.</p>
      <div className={cx('cta')}><Link className={cx('btn')} to="/login">Start building free</Link><a className={cx('btn ghost')} href="#journey">See how it fits together</a></div>
    </div><HomeHeroDemo /><p className={cx('trusted')}>Free to start · Runs on your own AI account · Undo anything in one step</p></div></header>

    <section className={cx('band')} id="journey"><div className={cx('wrap')}>
      <div className={cx('head rv centered')}><span className={cx('eyebrow')}>How it fits together</span><h2>Follow one customer<br />through your business.</h2><p className={cx('lead')}>Four things work as one. Tap any step to see how it works.</p></div>
      <HomeJourney /><div className={cx('built-by rv')}><StoryIcon name="sparkles" /><span>All of it was built from one conversation with <Link to="/features/ila">Ila</Link>.</span></div>
    </div></section>

    <section id="t-ila"><HomeGoals /></section>
    <section className={cx('band')} id="t-agents"><HomeAgents /></section>
    <section id="t-leads"><div className={cx('wrap split')}>
      <div className={cx('rv')}><span className={cx('chap eyebrow')}><b>3</b> Leads</span><h2>Turn visitors into leads.<br />Without a single form.</h2>
        <p className={cx('lead')}>Your agent chats, remembers, and saves a complete lead the moment it has what you need. Then your automations take over.</p><Link className={cx('more')} to="/features/leads">See how leads work <StoryIcon name="right" /></Link></div>
      <HomeLeadsDemo />
    </div></section>
    <section className={cx('band')} id="t-auto"><div className={cx('wrap split rev')}>
      <div className={cx('rv')}><span className={cx('chap eyebrow')}><b>4</b> Automations</span><h2>Your best employee<br />never clocks out.</h2>
        <p className={cx('lead')}>Put your agents on a schedule or on a trigger. Invoices get chased, emails get sorted, and your briefing is waiting when you wake.</p><Link className={cx('more')} to="/features/automations">Explore automations <StoryIcon name="right" /></Link></div>
      <HomeNightDemo />
    </div></section>

    <section id="start"><div className={cx('wrap')}>
      <div className={cx('head rv centered')}><span className={cx('eyebrow')}>Everything in one place</span><h2>And the parts that make it work.</h2></div>
      <div className={cx('box rv')}>{PARTS.map(([icon, label]) => <div key={label} className={cx('bx')}><StoryIcon name={icon} />{label}</div>)}</div>
      <div className={cx('final-space')} />
      <div className={cx('final rv')}><h2>Your AI team is<br /><span className={cx('grad')}>one conversation away.</span></h2><p className={cx('lead')}>Start free. Tell Ila about your business, and have something working before your coffee gets cold.</p><div className={cx('cta')}><Link className={cx('btn')} to="/login">Start building free</Link><Link className={cx('btn ghost')} to="/pricing">See pricing</Link></div></div>
      <div className={cx('next')}>{FEATURES.map(([route, icon, title, detail]) => <Link key={route} to={`/features/${route}`}><span className={cx('ic')}><StoryIcon name={icon} /></span><div><b>{title}</b><small>{detail}</small></div><span className={cx('go')}><StoryIcon name="right" /></span></Link>)}</div>
    </div></section>
  </StoryPage>;
}
