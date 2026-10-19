import { Fragment, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Link } from 'react-router-dom';
import { Input } from '../../components/ui/input';
import { StoryPage, StoryIcon, storyClasses } from '../../components/story/StoryPage';
import styles from './IlaPage.module.css';

const cx = storyClasses(styles);
const KINDS = {
  agent: ['bot', 'var(--gradient-start)', 'Agent'],
  knowledge: ['book', 'var(--amber)', 'Knowledge base'],
  leadform: ['inbox', 'var(--pink)', 'Lead form'],
  automation: ['clock', 'var(--teal)', 'Automation'],
  widget: ['globe', 'var(--green)', 'Chat widget'],
  skill: ['zap', 'var(--orange)', 'Skill'],
  connector: ['plug', 'var(--purple)', 'Connector'],
  secret: ['key', 'var(--red)', 'Secret'],
} as const;
type Kind = keyof typeof KINDS;
type PlanItem = readonly [Kind, string, string];

const HERO_PLAN: readonly PlanItem[] = [
  ['agent', 'Maple Concierge', 'Friendly, knows the shop'],
  ['knowledge', 'maplebakery.com', 'Menu, prices, allergens'],
  ['leadform', 'Wedding enquiry', 'Name, date, guests, budget'],
  ['automation', 'Morning summary', 'Every day at 08:00'],
  ['widget', 'Website chat', 'One snippet for your site'],
];
const HERO_CHAT = [
  'I want my bakery website to answer customer questions, collect wedding enquiries and email me a summary every morning.',
  'Here is my plan. Nothing changes until you approve it.',
  'Approved.',
  'Done. Everything is one kit, so you can change or undo it any time.',
];
const GOALS: { label: string; question: string; plan: readonly PlanItem[] }[] = [
  { label: 'Answer customers from my website', question: 'Answer customer questions from my website, day and night.', plan: [
    ['knowledge', 'maplebakery.com', 'Read the site, keep it fresh'],
    ['agent', 'Maple Concierge', 'Answers with links to the source'],
    ['widget', 'Website chat', 'One snippet for your site'],
  ] },
  { label: 'Capture leads and follow up', question: 'Capture wedding enquiries and follow up so none are missed.', plan: [
    ['leadform', 'Wedding enquiry', 'Name, date, guests, budget'],
    ['agent', 'Wedding Greeter', 'Asks naturally, remembers visitors'],
    ['automation', 'New lead follow-up', 'Email you, add to CRM'],
    ['connector', 'CRM', 'Connected once'],
  ] },
  { label: 'A weekly report in my inbox', question: 'Send me a short report of what happened every Monday.', plan: [
    ['agent', 'Weekly Digest', 'Writes what moved and why'],
    ['skill', 'Send email', 'Built in, no setup'],
    ['automation', 'Monday 08:00', 'Runs by itself'],
  ] },
];
const NEED_PLAN: readonly PlanItem[] = [
  ['automation', 'Morning summary', 'Reads supplier emails, adds leads'],
  ['connector', 'Gmail + CRM', 'Waiting for your sign-in and key'],
];
const PIECES: readonly (readonly [Kind, string, number])[] = [
  ['agent', 'Maple Concierge', 1], ['knowledge', 'maplebakery.com', 1],
  ['widget', 'Website chat', 1], ['leadform', 'Wedding enquiry', 2],
  ['automation', 'Morning summary', 3],
];
const PAGES = [
  ['guide/blueprint', 'How a blueprint works'], ['kind/Agent', 'Agents'],
  ['kind/KnowledgeBase', 'Knowledge bases'], ['kind/LeadForm', 'Lead forms'],
  ['kind/Automation', 'Automations'], ['skill/send_email', 'Skill: Send email'],
  ['skill/lead_capture', 'Skill: Lead capture'], ['recipe/website-assistant', 'Recipe: website assistant'],
];
const ASKS = [
  { label: 'Capture leads', pages: ['kind/Agent', 'kind/LeadForm', 'skill/lead_capture', 'kind/Automation'] },
  { label: 'Answer from my website', pages: ['kind/KnowledgeBase', 'kind/Agent', 'recipe/website-assistant'] },
  { label: 'Email me a report', pages: ['kind/Automation', 'skill/send_email'] },
];

function kindStyle(kind: Kind): CSSProperties {
  return { '--c': KINDS[kind][1] } as CSSProperties;
}

function subscribeMotion(onChange: () => void) {
  const query = window.matchMedia('(prefers-reduced-motion: reduce)');
  query.addEventListener('change', onChange);
  return () => query.removeEventListener('change', onChange);
}
function useReducedMotion() {
  return useSyncExternalStore(subscribeMotion,
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches, () => false);
}

// Each scene owns its clock; switching scenes or leaving the page cancels all work.
function useSceneClock(duration: number, active = true) {
  const reduced = useReducedMotion();
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (reduced || !active) return;
    const start = performance.now();
    const timer = window.setInterval(() => {
      const next = Math.min(performance.now() - start, duration);
      setElapsed(next);
      if (next >= duration) window.clearInterval(timer);
    }, 40);
    return () => window.clearInterval(timer);
  }, [duration, reduced, active]);
  return reduced ? duration : elapsed;
}

function useSeen() {
  const ref = useRef<HTMLDivElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    if (!ref.current) return;
    if (typeof IntersectionObserver === 'undefined') {
      const timer = window.setTimeout(() => setSeen(true), 0);
      return () => window.clearTimeout(timer);
    }
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        setSeen(true);
        observer.disconnect();
      }
    }, { threshold: 0.25 });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return { ref, seen };
}

function WindowBar({ children }: { children: ReactNode }) {
  return <div className={cx('bar')}><i /><i /><i /><span>{children}</span></div>;
}

function Plan({ items, shown = items.length, completed = 0, running = -1 }: {
  items: readonly PlanItem[]; shown?: number; completed?: number; running?: number;
}) {
  return <div className={cx('plan')}><div className={cx('chain')}>
    {items.map(([kind, name, detail], index) => <Fragment key={name}>
      {index > 0 && <div className={cx('link pre', index < shown && 'shown')} aria-hidden="true" />}
      <div className={cx('node pre', index < shown && 'shown', index < completed && 'ok', index === running && 'run')}
        style={kindStyle(kind)} aria-hidden={index >= shown}>
        <div className={cx('ic')}><StoryIcon name={KINDS[kind][0]} /></div>
        <div className={cx('t')}><small>{KINDS[kind][2]}</small><b>{name}</b><span>{detail}</span></div>
        <div className={cx('st')} aria-label={index < completed ? 'Built' : undefined}>✓</div>
      </div>
    </Fragment>)}
  </div></div>;
}

function Message({ text, user = false, elapsed, start, speed = 18 }: {
  text: string; user?: boolean; elapsed: number; start: number; speed?: number;
}) {
  const visible = elapsed >= start;
  const letters = Math.max(0, Math.min(text.length, Math.floor((elapsed - start) / speed)));
  const said = !user && elapsed >= start + 900;
  return <div className={cx('m pre', user ? 'u' : 'a', visible && 'shown', said && 'said', visible && !user && !said && 'thinking')}
    aria-hidden={!visible} aria-label={visible ? text : undefined}>
    {user ? <><span className={cx('tp')}>{text.slice(0, letters)}</span><span className={cx('tr')}>{text.slice(letters)}</span></>
      : <><span className={cx('tx')}>{text}</span><span className={cx('th dots')} aria-hidden="true"><i /><i /><i /></span></>}
  </div>;
}

function HeroDemo() {
  const firstEnd = HERO_CHAT[0].length * 22;
  const answerStart = firstEnd + 400;
  const planStart = answerStart + 900;
  const approvalStart = planStart + HERO_PLAN.length * 420;
  const autoBuildStart = approvalStart + 1800;
  const [approved, setApproved] = useState(false);
  const time = useSceneClock(autoBuildStart + 5 * 650 + 2200);
  const building = approved || time >= autoBuildStart;
  const buildTime = useSceneClock(5 * 650 + 1100, building);
  const built = building && buildTime >= 5 * 650;
  const reduced = useReducedMotion();
  const showApproval = time >= approvalStart && !building;
  const completed = building ? Math.min(5, Math.floor(buildTime / 650)) : 0;
  return <div className={cx('build')}>
      <div className={cx('chatcol')}><div className={cx('msgs')}>
        <Message text={HERO_CHAT[0]} user elapsed={time} start={0} speed={22} />
        <Message text={HERO_CHAT[1]} elapsed={time} start={answerStart} />
        <Message text={HERO_CHAT[2]} user elapsed={building ? buildTime : -1} start={0} />
        <Message text={HERO_CHAT[3]} elapsed={building ? buildTime : -1} start={3250} />
      </div></div>
      <div className={cx('plancol')}>
        <div className={cx('plan-h')}><StoryIcon name="layers" />Plan <span className={cx('ver', built && 'on')} aria-hidden={!built}>Kit v1 · built</span></div>
        <Plan items={HERO_PLAN} shown={reduced ? 5 : Math.max(0, Math.min(5, Math.floor((time - planStart) / 420) + 1))}
          completed={completed} running={building && !built ? completed : -1} />
        <div className={cx('approve')}>
          <button type="button" className={cx('btn pre', showApproval && 'shown')} tabIndex={showApproval ? 0 : -1}
            onClick={() => setApproved(true)}>Approve and build</button>
          <small className={cx('pre', showApproval && 'shown')}>5 things · about a minute</small>
        </div>
      </div>
  </div>;
}

function GoalScene({ goal, active, onShown }: { goal: typeof GOALS[number]; active: boolean; onShown: (count: number) => void }) {
  const clock = useSceneClock(4000, active);
  const time = active ? clock : -1;
  const answerStart = goal.question.length * 16;
  const planStart = answerStart + 900;
  const shown = Math.max(0, Math.min(goal.plan.length, Math.floor((time - planStart) / 380) + 1));
  useEffect(() => { if (active) onShown(shown); }, [active, shown, onShown]);
  return <div className={cx(active && 'on')} aria-hidden={!active} inert={!active}>
    <div className={cx('msgs goalMessages')}>
      <Message text={goal.question} user elapsed={time} start={0} speed={16} />
      <Message text="I would build this:" elapsed={time} start={answerStart} />
    </div>
    <Plan items={goal.plan} shown={shown} />
  </div>;
}

function GoalsDemo() {
  const [selected, setSelected] = useState(0);
  const [revision, setRevision] = useState(0);
  const [shown, setShown] = useState(0);
  const { ref, seen } = useSeen();
  return <section id="say"><div className={cx('wrap split')}>
    <div className={cx('rv')}>
      <span className={cx('chap eyebrow')}><b>1</b> Describe the outcome</span>
      <h2>Say the goal.<br />She picks the pieces.</h2>
      <p className={cx('lead')}>You do not need to know what a knowledge base or a trigger is. Ila chooses from everything InnomightLabs offers and shows you exactly what she would build. Try a goal.</p>
      <div className={cx('goals')} aria-label="Choose an example goal">{GOALS.map((goal, index) =>
        <button type="button" key={goal.label} className={cx('chipbtn', selected === index && 'on')} aria-pressed={selected === index}
          onClick={() => { setSelected(index); setShown(0); setRevision(value => value + 1); }}>{goal.label}</button>)}</div>
      <div className={cx('tray')}><small>Pieces Ila can use</small>{(Object.keys(KINDS) as Kind[]).map(kind =>
        <span key={kind} style={kindStyle(kind)} className={cx(GOALS[selected].plan.slice(0, shown).some(item => item[0] === kind) && 'on')}>
          <StoryIcon name={KINDS[kind][0]} />{KINDS[kind][2]}</span>)}</div>
    </div>
    <div className={cx('win rv')} ref={ref}><WindowBar>Ila</WindowBar><div className={cx('pad')}>
      <div className={cx('stack')} key={revision}>{GOALS.map((goal, index) =>
        <GoalScene key={goal.label} goal={goal} active={seen && selected === index} onShown={setShown} />)}</div>
    </div></div>
  </div></section>;
}

function NeedsDemo() {
  const [google, setGoogle] = useState(false);
  const [keySaved, setKeySaved] = useState(false);
  const [googleOpen, setGoogleOpen] = useState(false);
  const [keyOpen, setKeyOpen] = useState(false);
  const [building, setBuilding] = useState(false);
  const time = useSceneClock(1400, building);
  const completed = building ? Math.min(2, Math.floor(time / 700)) : 0;
  const built = completed === 2;
  return <section className={cx('band')} id="plan"><div className={cx('wrap split rev')}>
    <div className={cx('rv')}>
      <span className={cx('chap eyebrow')}><b>2</b> Review before anything changes</span>
      <h2>She only asks for<br />what she cannot do herself.</h2>
      <p className={cx('lead')}>Before building, Ila works out what she needs from you: a sign-in, a key, a yes. Each one appears right where you need it. Try the two below.</p>
      <div className={cx('vault')}><StoryIcon name="lock" /><span>Secrets go from the box straight to the vault. They never pass through the AI or your chat history.</span></div>
    </div>
    <div className={cx('win rv')}><WindowBar>Plan · Morning summary</WindowBar><div className={cx('pad')}>
      <div className={cx('needs')}>
        <div className={cx('need', google && 'done')}>
          <div className={cx('ic')}><StoryIcon name="mail" /></div><div><b>Connect your Gmail</b><small>To read supplier emails</small></div>
          <div className={cx('needAction')}><span className={cx('actionSizer')} aria-hidden="true">Sign in with Google</span>
          {google ? <span className={cx('connected')} role="status">✓ Connected</span> :
            <Dialog.Root open={googleOpen} onOpenChange={setGoogleOpen}>
              <Dialog.Trigger asChild><button type="button" className={cx('btn sm ghost')}>Sign in with Google</button></Dialog.Trigger>
              <Dialog.Overlay className={cx('dialogOverlay')} />
              <Dialog.Content className={cx('googlePopup')}>
                <Dialog.Title>Sign in with Google</Dialog.Title>
                <Dialog.Description>Maple &amp; Co. wants to read your supplier emails.</Dialog.Description>
                <p className={cx('demoNotice')}>Illustrative demo only. No account is connected.</p>
                <button type="button" onClick={() => { setGoogle(true); setGoogleOpen(false); }}>Allow</button>
                <Dialog.Close asChild><button type="button">Cancel</button></Dialog.Close>
              </Dialog.Content>
            </Dialog.Root>}</div>
        </div>
        <div className={cx('need', keySaved && 'done')}>
          <div className={cx('ic')}><StoryIcon name="key" /></div>
          <div><b>Your CRM API key</b><small>{keySaved ? <><span className={cx('secret')}>••••••••3f9a</span> saved to the vault</> : 'To add each new lead'}</small></div>
          <div className={cx('needAction')}><span className={cx('actionSizer')} aria-hidden="true">Enter key</span>
          {keySaved ? <span className={cx('connected')} role="status">✓ Saved</span> :
            <Dialog.Root open={keyOpen} onOpenChange={setKeyOpen}>
              <Dialog.Trigger asChild><button type="button" className={cx('btn sm ghost')}>Enter key</button></Dialog.Trigger>
              <Dialog.Overlay className={cx('dialogOverlay')} />
              <Dialog.Content className={cx('keySheet')}>
                <Dialog.Title>Your CRM API key</Dialog.Title>
                <Dialog.Description className={cx('demoNotice')}>Demo only: use a made-up key. Nothing is sent or stored.</Dialog.Description>
                <form onSubmit={event => { event.preventDefault(); event.currentTarget.reset(); setKeySaved(true); setKeyOpen(false); }}>
                  <div><label htmlFor="ila-demo-key">API key</label><Input id="ila-demo-key" name="demo-key" type="password" autoComplete="off" placeholder="Paste a sample key" required pattern={'.*\\S.*'} /></div>
                  <div className={cx('vault')}><StoryIcon name="lock" /><span>Saved straight to the vault. Ila never sees it.</span></div>
                  <div className={cx('dialogActions')}><button type="submit" className={cx('btn green')}>Save securely</button><Dialog.Close asChild><button type="button" className={cx('btn ghost')}>Cancel</button></Dialog.Close></div>
                </form>
              </Dialog.Content>
            </Dialog.Root>}</div>
        </div>
      </div>
      <div className={cx('miniPlan')}><Plan items={NEED_PLAN} completed={completed} running={building && !built ? completed : -1} /></div>
      <div className={cx('stack buildResult')} aria-live="polite">
        <button type="button" className={cx('btn', !built && 'on')} disabled={!google || !keySaved || building}
          tabIndex={built ? -1 : 0} aria-hidden={built} onClick={() => setBuilding(true)}>{building ? 'Building…' : 'Approve and build'}</button>
        <div className={cx('built', built && 'on')} aria-hidden={!built}>✓ Built as Kit v1. You can change or undo it any time.</div>
      </div>
    </div></div>
  </div></section>;
}

function KitDemo() {
  const [version, setVersion] = useState(1);
  const [removed, setRemoved] = useState(false);
  const [transition, setTransition] = useState<'rollback' | 'remove' | null>(null);
  const [note, setNote] = useState('Version 1 is what your first build created.');
  const reduced = useReducedMotion();
  useEffect(() => {
    if (!transition) return;
    const timer = window.setTimeout(() => {
      if (transition === 'remove') { setRemoved(true); setNote(''); }
      else { setVersion(value => value - 1); setNote(`Rolled back to v${version - 1}. The newer pieces are gone, the rest untouched.`); }
      setTransition(null);
    }, reduced ? 0 : transition === 'remove' ? 500 : 450);
    return () => window.clearTimeout(timer);
  }, [transition, reduced, version]);
  return <section id="kits"><div className={cx('wrap split')}>
    <div className={cx('rv')}>
      <span className={cx('chap eyebrow')}><b>3</b> Never stuck with it</span>
      <h2>Everything she builds is one kit.<br />Change it. Roll it back.</h2>
      <p className={cx('lead')}>A build is a kit with versions. Ask for a change and she adds a version. Not happy? Go back to any earlier one, or remove the whole thing in one step. Play with it.</p>
    </div>
    <div className={cx('kit rv')}>
      <div className={cx('hd')}><span className={cx('kitIcon')}><StoryIcon name="layers" /></span><b>Maple &amp; Co. kit</b>
        <div className={cx('vers')} aria-label={`Kit version ${version}`}>{[1, 2, 3].map(value => <span key={value} className={cx(value === version && 'on', value < version && 'past')} aria-current={value === version ? 'step' : undefined}>v{value}</span>)}</div>
      </div>
      <div className={cx('stack')}>
        <div className={cx('pieces', !removed && 'on')} aria-hidden={removed}>{PIECES.map(([kind, name, added]) => {
          const shown = !removed && added <= version;
          return <div key={name} style={kindStyle(kind)} aria-hidden={!shown}
            className={cx('piece pre', shown && 'shown', shown && version > 1 && added === version && 'fresh', shown && (transition === 'remove' || (transition === 'rollback' && added === version)) && 'gone')}>
            <div className={cx('ic')}><StoryIcon name={KINDS[kind][0]} /></div><div><b>{name}</b><small>{KINDS[kind][2]}</small></div>
          </div>;
        })}</div>
        <div className={cx('empty', removed && 'on')} aria-hidden={!removed}>Kit removed. Everything it created is gone in one step.</div>
      </div>
      <div className={cx('kitbtns')}>
        <button type="button" className={cx('btn sm')} disabled={removed || !!transition || version >= 3} onClick={() => {
          setVersion(value => value + 1); setNote(version === 1 ? 'Version 2: added a wedding enquiry form.' : 'Version 3: added a morning summary automation.');
        }}><StoryIcon name="plus" />Ask for a change</button>
        <button type="button" className={cx('btn sm ghost')} disabled={removed || !!transition || version <= 1} onClick={() => setTransition('rollback')}><StoryIcon name="undo" />Roll back</button>
        <button type="button" className={cx('btn sm ghost removeButton')} disabled={removed || !!transition} onClick={() => setTransition('remove')}>Remove kit</button>
        <button type="button" className={cx('btn sm ghost pre', removed && 'shown')} disabled={!removed} onClick={() => {
          setRemoved(false); setVersion(1); setNote('Rebuilt from the plan.');
        }}>↻ Rebuild</button>
      </div>
      <p className={cx('kitNote')} role="status">{note}</p>
    </div>
  </div></section>;
}

function BookDemo() {
  const [selected, setSelected] = useState(0);
  return <section className={cx('band')} id="book"><div className={cx('wrap book')}>
    <div className={cx('rv')}>
      <span className={cx('chap eyebrow')}><b>4</b> She knows the product</span>
      <h2>She reads the manual<br />so you do not have to.</h2>
      <p className={cx('lead')}>Ila keeps an index of everything the platform can do and opens the right pages as your request needs them. Add a feature, and she knows about it. Ask for something.</p>
      <div className={cx('asks')}><span className={cx('askLabel')}>She is asked:</span>{ASKS.map((ask, index) =>
        <button type="button" key={ask.label} className={cx('chipbtn', index === selected && 'on')} aria-pressed={index === selected} onClick={() => setSelected(index)}>{ask.label}</button>)}</div>
    </div>
    <div className={cx('win rv')}><WindowBar>Ila's book · index</WindowBar><div className={cx('pad index')}>
      {PAGES.map(([id, title]) => <div className={cx('page', ASKS[selected].pages.includes(id) && 'open')} key={id}>
        <code>{id}</code>{title}<em aria-hidden={!ASKS[selected].pages.includes(id)}>open for 3 turns</em>
      </div>)}
    </div></div>
  </div></section>;
}

export function IlaPage() {
  const [replay, setReplay] = useState(0);
  return <StoryPage title="Ila · Your solution builder | InnomightLabs" description="Tell Ila what you need. Review a plan, build your solution in one go, and change or undo it any time.">
    <header className={cx('hero')}><div className={cx('wrap')}>
      <div className={cx('intro')}>
        <span className={cx('eyebrow')}>Ila · your solution builder</span>
        <h1>Tell Ila what you need.<br /><span className={cx('grad')}>She builds it. You ship it.</span></h1>
        <p className={cx('lead')}>Agents, knowledge, lead forms, automations and a chat widget for your site: described in a conversation, reviewed as a plan, built in one go. Nothing changes until you say yes.</p>
        <div className={cx('cta')}><Link className={cx('btn')} to="/login">Start building free</Link><button type="button" className={cx('btn ghost')} onClick={() => setReplay(value => value + 1)}>↻ Watch it again</button></div>
      </div>
      <div className={cx('win rv')} aria-label="Illustrative bakery solution build">
        <WindowBar>Ila · Maple &amp; Co. Bakery</WindowBar>
        <HeroDemo key={replay} />
      </div>
    </div></header>
    <GoalsDemo />
    <NeedsDemo />
    <KitDemo />
    <BookDemo />
    <section id="trust"><div className={cx('wrap')}>
      <div className={cx('head rv')}><span className={cx('chap eyebrow')}><b>5</b> Built to be trusted</span><h2>Powerful, and in your hands.</h2></div>
      <div className={cx('trust rv')}>{[
        ['check', 'You approve everything', 'A plan first, a build second. Long texts show before and after.'],
        ['lock', 'Secrets stay secret', 'Keys are typed into a masked box and go straight to the vault.'],
        ['undo', 'Undo in one step', 'Roll back to any version, or remove all of it at once.'],
        ['key', 'Your own AI account', 'Ila runs on the provider and model you choose, with your key.'],
      ].map(([icon, title, text]) => <div className={cx('tc')} key={title}><div className={cx('ic')}><StoryIcon name={icon} /></div><b>{title}</b><p>{text}</p></div>)}</div>
    </div></section>
    <section id="start" className={cx('band')}><div className={cx('wrap')}>
      <div className={cx('outs rv')}>{['conversation to describe it', 'approval to build it', 'step to undo it'].map(text => <div className={cx('out')} key={text}><b className={cx('grad')}>1</b><span>{text}</span></div>)}</div>
      <div className={cx('final rv finalSpacing')}><h2>Describe your first solution.<br /><span className={cx('grad')}>Ila takes it from there.</span></h2>
        <p className={cx('lead finalLead')}>Start with one sentence about what you want your business to handle for you.</p>
        <div className={cx('cta')}><Link className={cx('btn')} to="/login">Start building free</Link><Link className={cx('btn ghost')} to="/">Back to all features</Link></div>
      </div>
      <div className={cx('next')}>{[
        ['agents', 'bot', 'Agents', 'What Ila builds with: your AI team'],
        ['leads', 'inbox', 'Leads', 'Turn conversations into customers'],
        ['automations', 'clock', 'Automations', 'Work that runs while you sleep'],
      ].map(([path, icon, title, subtitle]) => <Link key={path} to={`/features/${path}`}><span className={cx('ic')}><StoryIcon name={icon} /></span><div><b>{title}</b><small>{subtitle}</small></div><span className={cx('go')}><StoryIcon name="right" /></span></Link>)}</div>
    </div></section>
  </StoryPage>;
}
