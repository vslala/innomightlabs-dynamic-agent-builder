import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { StoryPage, StoryIcon, storyClasses } from '../../components/story/StoryPage';
import styles from './AgentsPage.module.css';
import { AGENTS, CREW, LAYERS, PEOPLE, SITE, buildAnswer, findAgents, type AgentFilter, type Layer } from './agentsDemo';

const cx = storyClasses(styles);
const color = (value: string) => ({ '--c': value } as CSSProperties);
const motionQuery = '(prefers-reduced-motion: reduce)';
function subscribeMotion(callback: () => void) {
  const media = window.matchMedia(motionQuery);
  media.addEventListener('change', callback);
  return () => media.removeEventListener('change', callback);
}
function useReducedMotion() {
  return useSyncExternalStore(subscribeMotion, () => window.matchMedia(motionQuery).matches, () => true);
}
function toggle<T>(values: ReadonlySet<T>, value: T): Set<T> {
  const next = new Set(values);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}
function WindowFrame({ title, children }: { title: string; children: ReactNode }) {
  return <div className={cx('win rv')}><div className={cx('bar')}><i /><i /><i /><span>{title}</span></div><div className={cx('pad')}>{children}</div></div>;
}
function Chapter({ number, children }: { number: number; children: ReactNode }) {
  return <span className={cx('chap eyebrow')}><b>{number}</b>{children}</span>;
}
function Source({ path }: { path: string }) {
  return <span className={cx('src')}><StoryIcon name="link" />maplebakery.com/{path}</span>;
}
function AgentCard({ name, icon, detail, tint }: { name: string; icon: string; detail: string; tint: string }) {
  return <div className={cx('agent')} style={color(tint)}><div className={cx('top')}><div className={cx('ic')}><StoryIcon name={icon} /></div><div><div className={cx('nm')}>{name}</div><div className={cx('by')}>{detail}</div></div></div></div>;
}
function Hero({ reduced }: { reduced: boolean }) {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (reduced || paused) return;
    const timer = window.setInterval(() => setActive(index => (index + 1) % CREW.length), 3200);
    return () => window.clearInterval(timer);
  }, [reduced, paused]);
  return <header className={cx('hero')}><div className={cx('wrap')}>
    <div className={cx('intro')}><span className={cx('eyebrow')}>Agents</span>
      <h1>An agent that<br /><span className={cx('rot')} aria-live={paused ? 'polite' : 'off'}>{CREW.map(([phrase], index) => <span key={phrase} className={cx('grad', index === active && 'on')} aria-hidden={index !== active}>{phrase}</span>)}</span></h1>
      <p className={cx('lead')}>Give each job its own agent. It knows your business, uses your tools, remembers your customers, and works while you do something else.</p>
      <div className={cx('cta')}><Link className={cx('btn')} to="/login">Create my first agent</Link><a className={cx('btn ghost')} href="#anatomy">See what is inside one</a></div>
    </div>
    <div className={cx('crew rv')}>{CREW.map(([, name, icon, tint, output], index) => <button type="button" key={name} className={cx('agent', index === active && 'on')} style={color(tint)} aria-pressed={index === active} onClick={() => { setActive(index); setPaused(true); }}>
      <span className={cx('top')}><span className={cx('ic')}><StoryIcon name={icon} /></span><span><span className={cx('nm')}>{name}</span><span className={cx('live')}>Working</span></span></span><span className={cx('out')}>{output}</span>
    </button>)}</div>
  </div></header>;
}
function TypedAnswer({ text, reduced, source }: { text: string; reduced: boolean; source: boolean }) {
  const [length, setLength] = useState(0);
  useEffect(() => {
    if (reduced) return;
    let count = 0;
    const timer = window.setInterval(() => {
      count = Math.min(count + 1, text.length);
      setLength(count);
      if (count === text.length) window.clearInterval(timer);
    }, 12);
    return () => window.clearInterval(timer);
  }, [text, reduced]);
  const shown = reduced ? text.length : length;
  return <div className={cx('m a on fullBubble')} aria-label={text}><span aria-hidden="true">{text.slice(0, shown)}<span className={cx('untyped')}>{text.slice(shown)}</span></span>{source && <span className={cx(shown !== text.length && 'untyped')}><Source path="menu" /></span>}</div>;
}
function Anatomy({ reduced }: { reduced: boolean }) {
  const [layers, setLayers] = useState<Set<Layer>>(new Set(['knowledge']));
  const text = buildAnswer(layers);
  return <section id="anatomy"><div className={cx('wrap split')}>
    <div className={cx('rv')}><Chapter number={1}>What makes it good</Chapter><h2>Same agent. Add a layer,<br />watch it get smarter.</h2>
      <p className={cx('lead')}>A plain agent can only chat. Give it your knowledge, your tools and a memory, and the same question gets a real answer. Flip the switches.</p>
      <div className={cx('layers')}>{LAYERS.map(([key, icon, tint, title, description]) => <button type="button" key={key} className={cx('layer', layers.has(key) && 'on')} style={color(tint)} aria-pressed={layers.has(key)} onClick={() => setLayers(current => toggle(current, key))}>
        <span className={cx('ic')}><StoryIcon name={icon} /></span><span><b>{title}</b><small>{description}</small></span><span className={cx('sw')} aria-hidden="true" />
      </button>)}</div>
    </div>
    <WindowFrame title="Maple Concierge"><div className={cx('asked')}>Sarah asks:</div><div className={cx('msgs')}>
      <div className={cx('m u fullBubble')}>Do you have gluten free options? I need something for Saturday.</div>
      <div className={cx('stack')}>
        {/* Both longest variants reserve space, including when knowledge is disabled. */}
        <div className={cx('m a fullBubble')} aria-hidden="true">{buildAnswer(new Set(LAYERS.map(([key]) => key)))}<Source path="menu" /></div>
        <div className={cx('m a fullBubble')} aria-hidden="true">{buildAnswer(new Set(['skills', 'connector', 'memory']))}</div>
        <TypedAnswer key={text} text={text} reduced={reduced} source={layers.has('knowledge')} />
      </div>
    </div><div className={cx('meter')} aria-live="polite">Usefulness <b>{['Basic', 'Helpful', 'Very helpful', 'Like a regular employee', 'Like your best employee'][layers.size]}</b></div></WindowFrame>
  </div></section>;
}
function Knowledge({ reduced }: { reduced: boolean }) {
  const [url, setUrl] = useState('maplebakery.com');
  const [site, setSite] = useState('maplebakery.com');
  const [started, setStarted] = useState(false);
  const [run, setRun] = useState(0);
  const [step, setStep] = useState(0);
  const [phase, setPhase] = useState(0);
  const frame = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = frame.current;
    if (!element) return;
    if (typeof IntersectionObserver === 'undefined') {
      const timer = window.setTimeout(() => setStarted(true), 0);
      return () => window.clearTimeout(timer);
    }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { setStarted(true); observer.disconnect(); }
    }, { threshold: 0.15 });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!started || reduced) return;
    const timers = SITE.map((_, index) => window.setTimeout(() => setStep(index + 1), index * 230));
    timers.push(window.setTimeout(() => setPhase(1), SITE.length * 230 + 400));
    timers.push(window.setTimeout(() => setPhase(2), SITE.length * 230 + 1400));
    return () => timers.forEach(timer => window.clearTimeout(timer));
  }, [started, run, reduced]);
  function replay() { setSite(url.trim() || 'maplebakery.com'); setStep(0); setPhase(0); setStarted(true); setRun(value => value + 1); }
  const currentStep = reduced && started ? SITE.length : step;
  const currentPhase = reduced && started ? 2 : phase;
  const pages = Math.round(currentStep / SITE.length * 38);
  return <section className={cx('band')} id="know"><div className={cx('wrap split rev')}>
    <div className={cx('rv')}><Chapter number={2}>Teach it your business</Chapter><h2>Point it at your website.<br />It reads every page.</h2>
      <p className={cx('lead')}>Give an agent your site or documents and it answers from them, with a link back to the source. It re-reads on a schedule, so answers stay fresh when your prices change.</p>
      <button type="button" className={cx('btn ghost sm')} onClick={replay}>↻ Replay</button>
    </div>
    <div ref={frame}><WindowFrame title="Knowledge base">
      <form className={cx('urlbar')} onSubmit={event => { event.preventDefault(); replay(); }}><input value={url} onChange={event => setUrl(event.target.value)} aria-label="Website address" /><button type="submit" className={cx('btn')}>Read it</button></form>
      <div className={cx('pages')} aria-label="Illustrative pages read">{SITE.slice(0, currentStep).reverse().map(path => <div key={`${run}-${path}`}><StoryIcon name="check" /><span>{site}{path}</span><small>read</small></div>)}</div>
      <div className={cx('bigs')}><div><b>{pages}</b><small>pages read</small></div><div><b>{pages * 11}</b><small>sections learned</small></div></div>
      <div className={cx('bar2')} role="progressbar" aria-label="Website reading progress" aria-valuenow={Math.round(currentStep / SITE.length * 100)} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${currentStep / SITE.length * 100}%` }} /></div>
      <div className={cx('qa')}><div className={cx('msgs')} aria-live="polite"><div className={cx('m u pre', currentPhase >= 1 && 'shown')} aria-hidden={currentPhase < 1}>What time do you open on Sundays?</div><div className={cx('m a pre said', currentPhase >= 2 && 'shown')} aria-hidden={currentPhase < 2}>We open at 8am on Sundays and close at 2pm. <Source path="hours" /></div></div></div>
    </WindowFrame></div>
  </div></section>;
}
function Sharing() {
  const [shared, setShared] = useState(new Set([1]));
  return <section id="share"><div className={cx('wrap split')}>
    <div className={cx('rv')}><Chapter number={3}>Share with the right people</Chapter><h2>Your team gets the agent.<br />You keep the controls.</h2>
      <p className={cx('lead')}>Share an agent with a person or a whole group. They find it on their own dashboard and chat with it, and you decide who can change it. Choose who gets this one.</p>
      <div className={cx('acc')}><span>Owner: full control</span><span>Shared: can chat</span><span>Admin: sees it exists, not the contents</span></div>
    </div>
    <WindowFrame title="Share · Invoice Chaser"><div className={cx('people')}>{PEOPLE.map(([name, role, initials, tint], index) => <button type="button" key={name} className={cx('person', shared.has(index) && 'on')} aria-pressed={shared.has(index)} onClick={() => setShared(current => toggle(current, index))}>
      <i style={{ background: tint }}>{initials}</i><span><b>{name}</b><small>{role}</small></span><span className={cx('ck')} aria-hidden="true">✓</span>
    </button>)}</div><div className={cx('dash')}><h4>Jon's dashboard · Shared with me</h4><div className={cx('stack')} aria-live="polite">
      <div className={cx(shared.has(0) && 'on')} aria-hidden={!shared.has(0)}><AgentCard name="Invoice Chaser" icon="file" tint="var(--pink)" detail="by You · Shared with me" /></div>
      <div className={cx('none', !shared.has(0) && 'on')} aria-hidden={shared.has(0)}>Nothing shared with Jon yet. Select Jon above.</div>
    </div></div></WindowFrame>
  </div></section>;
}
const PLACEMENTS = [['web', 'Website widget'], ['api', 'Public API'], ['a2a', 'Other agents']] as const;
function Delivery({ reduced }: { reduced: boolean }) {
  const [tab, setTab] = useState<'web' | 'api' | 'a2a'>('web');
  const [open, setOpen] = useState(false);
  const [reply, setReply] = useState(false);
  const launcher = useRef<HTMLButtonElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    close.current?.focus();
    const trigger = launcher.current;
    const timer = reduced ? undefined : window.setTimeout(() => setReply(true), 700);
    return () => {
      if (timer !== undefined) window.clearTimeout(timer);
      trigger?.focus();
    };
  }, [open, reduced]);
  function closeChat() { setOpen(false); setReply(false); }
  return <section className={cx('band')} id="deliver"><div className={cx('wrap')}>
    <div className={cx('head rv')}><Chapter number={4}>Put it anywhere</Chapter><h2>One agent. Every place your customers are.</h2><p className={cx('lead')}>Drop a chat widget on your website, call it from your own software, or let your other agents ask it for help.</p></div>
    <WindowFrame title="Maple Concierge · Deliver"><div className={cx('tabs')} role="tablist" aria-label="Agent placement">{PLACEMENTS.map(([id, label], index) => <button type="button" key={id} id={`agents-tab-${id}`} role="tab" aria-selected={tab === id} aria-controls={`agents-pane-${id}`} tabIndex={tab === id ? 0 : -1} className={cx('chipbtn', tab === id && 'on')} onClick={() => setTab(id)} onKeyDown={event => {
      let next = index;
      if (event.key === 'ArrowRight') next = (index + 1) % PLACEMENTS.length;
      else if (event.key === 'ArrowLeft') next = (index + PLACEMENTS.length - 1) % PLACEMENTS.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = PLACEMENTS.length - 1;
      else return;
      event.preventDefault(); setTab(PLACEMENTS[next][0]); document.getElementById(`agents-tab-${PLACEMENTS[next][0]}`)?.focus();
    }}>{label}</button>)}</div>
      <div className={cx('stack deliveryStack')}>
        <div className={cx('pane', tab === 'web' && 'on')} id="agents-pane-web" role="tabpanel" aria-labelledby="agents-tab-web" aria-hidden={tab !== 'web'} inert={tab !== 'web'}><div className={cx('shop')}><h4>Maple &amp; Co. Bakery</h4><p>Fresh bread since 1998. Order for Saturday!</p><div className={cx('menu')} aria-hidden="true"><div /><div /><div /></div>
          <button ref={launcher} type="button" className={cx('launcher', open && 'untyped')} aria-label="Open chat" aria-expanded={open} aria-controls="agents-widget" disabled={open} onClick={() => setOpen(true)}>💬</button>
          <div id="agents-widget" className={cx('widget', open && 'open')} role="region" aria-label="Maple Concierge chat demo" onKeyDown={event => { if (event.key === 'Escape') closeChat(); }}><header><span className={cx('botIcon')}><StoryIcon name="bot" /></span>Maple Concierge<button ref={close} type="button" aria-label="Close chat" onClick={closeChat}>✕</button></header><div className={cx('msgs')} aria-live="polite"><div className={cx('m u')}>Is the almond cake gluten free?</div><div className={cx('m a pre said', (reply || reduced) && 'shown')} aria-hidden={!reply && !reduced}>Yes, and it is $4.50. Want me to set one aside for Saturday?</div></div></div>
        </div><p className={cx('widgetHint')}>Tap the chat bubble. One snippet on your site, no developer needed.</p></div>
        <div className={cx('pane', tab === 'api' && 'on')} id="agents-pane-api" role="tabpanel" aria-labelledby="agents-tab-api" aria-hidden={tab !== 'api'} inert={tab !== 'api'}><pre className={cx('code')}><span className={cx('c')}># Ask your agent from your own software</span>{'\n'}curl https://api.innomightlabs.com/v1/agents/<span className={cx('s')}>maple-concierge</span>/chat {'\\\n'}  -H <span className={cx('s')}>{'"Authorization: Bearer $KEY"'}</span> {'\\\n'}  -d <span className={cx('s')}>{`'{"message": "Is the almond cake gluten free?"}'`}</span>{'\n\n'}<span className={cx('c')}># Reply</span>{'\n{ '}<span className={cx('k')}>"reply"</span>: <span className={cx('s')}>"Yes, and it is $4.50. Want me to set one aside?"</span>{',\n  '}<span className={cx('k')}>"sources"</span>: [<span className={cx('s')}>"maplebakery.com/menu"</span>]{' }'}</pre></div>
        <div className={cx('pane', tab === 'a2a' && 'on')} id="agents-pane-a2a" role="tabpanel" aria-labelledby="agents-tab-a2a" aria-hidden={tab !== 'a2a'} inert={tab !== 'a2a'}><div className={cx('a2a')}><AgentCard name="Lead Scout" icon="search" tint="var(--green)" detail="needs the invoice history" /><div className={cx('arrow')}>↓ asks, agent to agent ↓</div><AgentCard name="Invoice Chaser" icon="file" tint="var(--pink)" detail={'"Acme paid 3 of 4 invoices on time."'} /></div></div>
      </div>
    </WindowFrame>
  </div></section>;
}
function Highlight({ text, query }: { text: string; query: string }) {
  const words = query.trim().split(/\s+/).map(word => word.replace(/[^\w]/g, '')).filter(Boolean);
  if (!words.length) return text;
  const pattern = new RegExp(`(${words.join('|')})`, 'ig');
  return text.split(pattern).map((part, index) => index % 2 ? <mark key={index} className={cx('match')}>{part}</mark> : part);
}
const FILTERS = [['kb', 'book', 'Knowledge'], ['conn', 'plug', 'Connectors'], ['skill', 'zap', 'Skills']] as const;
function Finder({ reduced }: { reduced: boolean }) {
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState<Set<AgentFilter>>(new Set());
  const [favorites, setFavorites] = useState(new Set(AGENTS.filter(agent => agent.favorite).map(agent => agent.id)));
  const search = useRef<HTMLInputElement>(null);
  const section = useRef<HTMLElement>(null);
  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); section.current?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth' }); search.current?.focus({ preventScroll: true });
      }
    }
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  }, [reduced]);
  const hits = findAgents(query, filters, favorites);
  return <section id="find" ref={section}><div className={cx('wrap split')}>
    <div className={cx('rv')}><Chapter number={5}>It scales with you</Chapter><h2>Hundreds of agents.<br />Still one keystroke away.</h2><p className={cx('lead')}>Search by what an agent does, filter by what it has, and star the ones you use daily. On a keyboard, press <code>⌘K</code> from anywhere. Try typing "inv" or filter by knowledge.</p></div>
    <WindowFrame title="Agents"><div className={cx('finder')}><label className={cx('search')}><StoryIcon name="search" /><input ref={search} value={query} onChange={event => setQuery(event.target.value)} placeholder="Search 240 agents" aria-label="Search agents" autoComplete="off" /><kbd>⌘K</kbd></label>
      <div className={cx('has')}><span>Has</span>{FILTERS.map(([key, icon, label]) => <button type="button" key={key} className={cx('chipbtn', filters.has(key) && 'on')} aria-pressed={filters.has(key)} onClick={() => setFilters(current => toggle(current, key))}><StoryIcon name={icon} />{label}</button>)}</div>
      <div className={cx('count')} role="status"><b>{hits.length}</b> of {AGENTS.length} agents</div><div className={cx('list')}>{hits.slice(0, 6).map(agent => <div key={agent.id} className={cx('row')} style={color(agent.color)}><div className={cx('ic')}><StoryIcon name={agent.icon} /></div><div><b><Highlight text={agent.name} query={query} /></b><small>by {agent.owner}</small></div><div className={cx('tg')}><button type="button" className={cx('favorite', favorites.has(agent.id) && 'star')} aria-label={`${favorites.has(agent.id) ? 'Unstar' : 'Star'} ${agent.name}`} aria-pressed={favorites.has(agent.id)} onClick={() => setFavorites(current => toggle(current, agent.id))}><StoryIcon name="star" /></button>{agent.kb && <span title="Knowledge"><StoryIcon name="book" /></span>}{agent.conn && <span title="Connectors"><StoryIcon name="plug" /></span>}{agent.skill && <span title="Skills"><StoryIcon name="zap" /></span>}</div></div>)}{!hits.length && <div className={cx('none')}>No agent matches. Try fewer words.</div>}</div>
    </div></WindowFrame>
  </div></section>;
}
function Start() {
  return <section id="start" className={cx('band')}><div className={cx('wrap')}><div className={cx('outs rv')}>{[['1', 'sentence to start an agent'], ['100s', 'of agents, still easy to find'], ['0', 'lines of code to deliver it']].map(([number, label]) => <div key={number} className={cx('out')}><b className={cx('grad')}>{number}</b><span>{label}</span></div>)}</div>
    <div className={cx('final rv finalGap')}><h2>Your first agent is<br /><span className={cx('grad')}>one sentence away.</span></h2><p className={cx('lead centeredLead')}>Describe the job. Ila builds the agent, and its card lands on your dashboard ready to chat.</p><div className={cx('cta')}><Link className={cx('btn')} to="/login">Create my first agent, free</Link><Link className={cx('btn ghost')} to="/">Back to all features</Link></div></div>
    <div className={cx('next')}>{[['ila', 'sparkles', 'Ila', 'Let her build your agents'], ['leads', 'inbox', 'Leads', 'Agents that capture customers'], ['automations', 'clock', 'Automations', 'Put agents to work on a schedule']].map(([route, icon, title, subtitle]) => <Link to={`/features/${route}`} key={route}><span className={cx('ic')}><StoryIcon name={icon} /></span><div><b>{title}</b><small>{subtitle}</small></div><span className={cx('go')}><StoryIcon name="right" /></span></Link>)}</div>
  </div></section>;
}
export function AgentsPage() {
  const reduced = useReducedMotion();
  return <StoryPage title="Agents — InnomightLabs" description="Give each job its own agent. It knows your business, uses your tools, remembers your customers, and works while you do something else."><Hero reduced={reduced} /><Anatomy reduced={reduced} /><Knowledge reduced={reduced} /><Sharing /><Delivery reduced={reduced} /><Finder reduced={reduced} /><Start /></StoryPage>;
}
