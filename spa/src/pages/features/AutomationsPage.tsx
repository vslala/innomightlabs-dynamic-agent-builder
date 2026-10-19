import { Fragment, useEffect, useRef, useState } from 'react';
import { StoryPage, StoryIcon, storyClasses } from '../../components/story/StoryPage';
import { NextFeatures, Recipe, RecipeNode, WindowBar, type DemoNode } from './featureDemos';
import { nodeColor, useDemoClock, useReducedMotion } from './featureDemoTiming';
import styles from './AutomationsPage.module.css';

const cx = storyClasses(styles);
const nightEvents = [
  { at: 90, color: 'teal', icon: 'file', title: 'Receipts filed', detail: '14 emailed receipts matched to expenses', time: '23:30' },
  { at: 240, color: 'purple', icon: 'mail', title: 'Inbox sorted', detail: '12 supplier emails, 1 flagged urgent', time: '02:00' },
  { at: 465, color: 'pink', icon: 'clock', title: 'Late invoices nudged', detail: '4 polite reminders sent', time: '05:45' },
  { at: 540, color: 'amber', icon: 'cal', title: "Today's orders checked", detail: '3 pickups, 1 large order to prepare', time: '07:00' },
  { at: 600, color: 'green', icon: 'sparkles', title: 'Morning briefing sent', detail: 'Waiting in your inbox', time: '08:00' },
];
const sayText = 'Every weekday at 8am, ask my Booking agent what is happening tomorrow and email me the summary.';
const sayNodes: DemoNode[] = [
  { color: 'teal', icon: 'clock', label: 'When', title: 'Weekdays at 08:00', detail: 'Europe/London' },
  { color: 'gradient-start', icon: 'bot', label: 'Then', title: 'Ask Booking Assistant', detail: '“What is happening tomorrow?”' },
  { color: 'green', icon: 'mail', label: 'Then', title: 'Email you the reply', detail: <>Body: <span className={cx('chip')}>Reply from Booking Assistant</span></> },
  { color: 'text-muted', icon: 'flag', label: 'Done', title: 'All set' },
];
const kinds = {
  agent: { label: 'Ask an agent', icon: 'bot', color: 'gradient-start', title: 'Ask an agent', detail: 'Prompt: “Summarise this week”' },
  email: { label: 'Send an email', icon: 'mail', color: 'green', title: 'Send an email', detail: 'Body: ' },
  gmail: { label: 'Search Gmail', icon: 'search', color: 'orange', title: 'Search Gmail', detail: 'Query: from:suppliers newer_than:7d' },
  api: { label: 'Call an API', icon: 'plug', color: 'teal', title: 'Call your shop API', detail: 'GET /orders?status=open' },
  branch: { label: 'Add IF / ELSE', icon: 'branch', color: 'purple', title: 'IF something is found', detail: '' },
};
type StepKind = keyof typeof kinds;
type Run = { id: number; name: string; passed: boolean; running?: boolean; steps: { title: string; io: string; failed?: boolean }[] };
const initialRuns: Run[] = [
  { id: 0, name: 'Today 08:00', passed: true, steps: [{ title: 'Find overdue invoices', io: 'Received: status = overdue\nReturned: 4 invoices' }, { title: 'Ask Invoice Chaser', io: 'Received: 4 invoices\nReturned: 4 polite drafts' }, { title: 'Send emails', io: 'Sent 4 of 4' }] },
  { id: 1, name: 'Yesterday 08:00', passed: true, steps: [{ title: 'Find overdue invoices', io: 'Returned: 2 invoices' }, { title: 'Ask Invoice Chaser', io: 'Returned: 2 polite drafts' }, { title: 'Send emails', io: 'Sent 2 of 2' }] },
  { id: 2, name: 'Tue 08:00', passed: false, steps: [{ title: 'Find overdue invoices', io: 'Returned: 3 invoices' }, { title: 'Ask Invoice Chaser', io: 'Returned: 3 drafts' }, { title: 'Send emails', io: 'Failed: recipient address for Bolt & Co. is missing', failed: true }] },
  { id: 3, name: 'Mon 08:00', passed: true, steps: [{ title: 'Find overdue invoices', io: 'Returned: 5 invoices' }, { title: 'Ask Invoice Chaser', io: 'Returned: 5 drafts' }, { title: 'Send emails', io: 'Sent 5 of 5' }] },
];
const templates = [
  { name: 'Daily briefing', description: 'Every morning your agent writes a short briefing and emails it to you.', icon: 'mail', color: 'gradient-start', meta: '2 steps · schedule' },
  { name: 'Lead follow-up', description: 'When a new lead arrives, an agent replies within a minute and tells you.', icon: 'zap', color: 'green', meta: '3 steps · on event' },
  { name: 'Overdue invoice nudge', description: 'Finds late invoices and sends a polite, personal reminder.', icon: 'file', color: 'pink', meta: '3 steps · schedule' },
  { name: 'Weekly report', description: "Pulls the week's numbers and writes what moved, and why.", icon: 'cal', color: 'amber', meta: '4 steps · schedule' },
  { name: 'Review responder', description: 'Drafts a reply to every new review, ready for your approval.', icon: 'bot', color: 'purple', meta: '3 steps · IF / ELSE' },
  { name: 'Supplier inbox triage', description: 'Sorts supplier emails and flags anything urgent.', icon: 'search', color: 'orange', meta: '3 steps · schedule' },
];

function Night() {
  const { attach: demoRef, elapsed: demoElapsed, reduced: demoReduced } = useDemoClock(18500, true);
  const minutes = demoReduced ? 600 : Math.min(600, demoElapsed / 14000 * 600);
  const hour = Math.floor((22 * 60 + minutes) / 60) % 24;
  const minute = Math.floor((22 * 60 + minutes) % 60);
  return <div ref={demoRef} className={cx('night rv')} aria-label="One night of automations"><div className={cx('sky')}><div className={cx('stars')} style={{ opacity: Math.max(0, .85 - minutes / 600) }} /><div className={cx('orb')} style={{ left: `calc(16px + (100% - 32px) * ${minutes / 600})` }}>{minutes > 520 ? '☀️' : '🌙'}</div><div className={cx('owner')}>{minutes > 570 ? 'You: ☕ awake, briefing ready' : 'You: 😴 asleep'}</div><div className={cx('clock')}><b>{String(hour).padStart(2, '0')}:{String(minute).padStart(2, '0')}</b><small>Maple &amp; Co. Bakery</small></div><div className={cx('track')}><div className={cx('fill')} style={{ width: `${minutes / 6}%` }} />{nightEvents.map(event => <i key={event.at} className={cx('dot', minutes >= event.at && 'on')} style={{ ...nodeColor(event.color), left: `${event.at / 6}%` }} />)}</div></div><ul className={cx('done-list')}>{nightEvents.map(event => <li key={event.at} className={cx(minutes >= event.at && 'on')} style={nodeColor(event.color)}><div className={cx('ic')}><StoryIcon name={event.icon} /></div><div><b>{event.title}</b><small>{event.detail}</small></div><time>{event.time}</time></li>)}</ul></div>;
}
function SayIt() {
  const typedAt = sayText.length * 28;
  const revealAt = typedAt + 500;
  const runAt = revealAt + sayNodes.length * 520 + 700;
  const duration = runAt + sayNodes.length * 750;
  const { attach: demoRef, elapsed: demoElapsed, replay: replayDemo } = useDemoClock(duration);
  const count = Math.min(sayText.length, Math.floor(demoElapsed / 28));
  return <section id="say"><div className={cx('wrap split')}><div className={cx('rv')}><span className={cx('chap eyebrow')}><b>1</b> Describe it</span><h2>Say it like you would<br />to a person.</h2><p className={cx('lead')}>No flowcharts to draw. Write what should happen and when. Ila drafts the steps, you adjust anything, and test it before it goes live.</p><button type="button" className={cx('btn ghost sm')} onClick={replayDemo}>↻ Replay</button></div><div className={cx('win rv')} ref={demoRef}><WindowBar cx={cx} title="New automation" /><div className={cx('pad')}><div className={cx('say')}><span className={cx('tp', count < sayText.length && 'caret')}>{sayText.slice(0, count)}</span><span className={cx('tr')}>{sayText.slice(count)}</span></div><div className={cx('say-gap')} /><div className={cx('tagline', demoElapsed < revealAt && 'concealed')}><StoryIcon name="sparkles" /> Ila drafted this. Edit anything.</div><Recipe cx={cx} nodes={sayNodes} elapsed={demoElapsed} revealAt={revealAt} runAt={runAt} /><div className={cx('mail pre', demoElapsed >= duration && 'shown')}><span className={cx('ic')}>✉️</span><div><b>Tomorrow at a glance</b><br /><span className={cx('muted')}>3 pickups, 1 big order, 2 new tastings</span></div></div></div></div></div></section>;
}
function Builder() {
  const [steps, setSteps] = useState<{ kind: StepKind; id: number }[]>([{ kind: 'agent', id: 0 }, { kind: 'email', id: 1 }]);
  const nextId = useRef(2);
  return <section className={cx('band')} id="build"><div className={cx('wrap split rev')}><div className={cx('rv')}><span className={cx('chap eyebrow')}><b>2</b> Build it your way</span><h2>It reads like a recipe.<br />Add a step, done.</h2><p className={cx('lead')}>WHEN something starts, THEN steps run one after another. Each step can ask an agent, send an email, search your Gmail or call another tool, and use what the last one found. Try building one.</p><div className={cx('palette')}>{(Object.keys(kinds) as StepKind[]).map(kind => <button type="button" key={kind} className={cx('pal')} disabled={steps.length >= 6} onClick={() => { const id = nextId.current++; setSteps(previous => previous.length < 6 ? [...previous, { kind, id }] : previous); }}><StoryIcon name={kinds[kind].icon} />{kinds[kind].label}</button>)}</div><button type="button" className={cx('btn ghost sm')} onClick={() => setSteps([{ kind: 'agent', id: nextId.current++ }, { kind: 'email', id: nextId.current++ }])}>↻ Start over</button></div><div className={cx('win rv')}><WindowBar cx={cx} title="Weekly digest" /><div className={cx('pad')}><div className={cx('chainbox')}><div className={cx('chain')}><RecipeNode cx={cx} item={{ color: 'teal', icon: 'clock', label: 'When', title: 'Fridays at 16:00', detail: 'Europe/London' }} />{steps.map((step, index) => {
    const kind = kinds[step.kind];
    const detail = step.kind === 'email' ? <>Body: {steps.some(item => item.kind === 'agent') ? <span className={cx('chip')}>Reply from “Ask an agent”</span> : <i>(add an agent step first)</i>}</> : kind.detail;
    return <Fragment key={step.id}><div className={cx('link')} /><RecipeNode cx={cx} item={{ ...kind, label: `Then · step ${index + 1}`, detail }} remove={() => setSteps(previous => previous.filter(item => item.id !== step.id))}>{step.kind === 'branch' && <div className={cx('branch')}><div><b>Yes</b>Carry on</div><div><b>No</b>Stop here</div></div>}</RecipeNode></Fragment>;
  })}<div className={cx('link')} /><RecipeNode cx={cx} item={{ color: 'text-muted', icon: 'flag', label: 'Done', title: 'End' }} /></div></div><p className={cx('hint')} aria-live="polite">{steps.length >= 6 ? 'That is plenty for one automation.' : steps.length === 0 ? 'Add your first step above.' : 'Tap × on a step to remove it.'}</p></div></div></div></section>;
}
function Triggers() {
  const { attach: demoRef, elapsed: demoElapsed, reduced: demoReduced } = useDemoClock(6300, true);
  const reduced = useReducedMotion();
  const [test, setTest] = useState<'idle' | 'running' | 'passed'>('idle');
  useEffect(() => {
    if (test !== 'running') return;
    const timer = setTimeout(() => setTest('passed'), reduced ? 0 : 2500);
    return () => clearTimeout(timer);
  }, [test, reduced]);
  const day = demoReduced ? 0 : Math.floor(demoElapsed / 900) % 7;
  return <section><div className={cx('wrap')}><div className={cx('head trigger-head rv')}><span className={cx('chap eyebrow')}><b>3</b> Start it any way</span><h2>On a schedule. When something happens. Or when you say so.</h2><p className={cx('lead')}>One automation can have several triggers. Pick the ones that fit the job.</p></div><div className={cx('three')} ref={demoRef}>
    <div className={cx('tcard rv')}><div className={cx('demo')}><div className={cx('week')}>{['M', 'T', 'W', 'T', 'F', 'S', 'S'].map((label, index) => <div key={index} className={cx(index < 5 && 'wk', day === index && index < 5 && 'hit')}>{label}<small>08:00</small></div>)}</div><div className={cx('center')}><code>0 8 * * 1-5</code></div></div><h3>On a schedule</h3><p>Every weekday at 8, the 1st of the month, every 15 minutes. In your own timezone. Say it in plain English and Ila writes the schedule.</p></div>
    <div className={cx('tcard rv')}><div className={cx('demo')}><div className={cx('toast t1')}><b>New lead captured</b><br /><small className={cx('muted')}>Priya, wedding cake enquiry</small></div><div className={cx('toast t2')}><b>Agent replied in 38s</b><br /><small className={cx('muted')}>Sent a tasting invite</small></div><div className={cx('toast t3')}><b>Added to your follow-up list</b></div></div><h3>When something happens</h3><p>A new lead comes in and your agent replies in under a minute, even at 2am on a Sunday.</p></div>
    <div className={cx('tcard rv')}><div className={cx('demo')}><div className={cx('meter')}><i key={test} className={cx(test === 'running' && 'testProgress', test === 'passed' && 'complete')} /></div><div className={cx('tmsg')} role="status">{test === 'idle' ? 'Never run before' : test === 'running' ? 'Running…' : <><span className={cx('success')}>✓ Passed in 2.4s</span> · 3 of 3 steps</>}</div><div className={cx('center')}><button type="button" className={cx('btn sm')} disabled={test === 'running'} onClick={() => setTest('running')}><StoryIcon name="play" /> Test</button></div></div><h3>When you say so</h3><p>Press Test and watch every step run. Safe to try any time, even on a draft.</p></div>
  </div></div></section>;
}
function Decisions() {
  const [amount, setAmount] = useState(320);
  const big = amount > 500;
  return <section className={cx('band')}><div className={cx('wrap')}><div className={cx('head trigger-head rv')}><span className={cx('chap eyebrow')}><b>4</b> Let it decide</span><h2>Routine work runs itself.<br />Big decisions come to you.</h2><p className={cx('lead')}>Add an IF / ELSE and the automation takes a different path depending on what it finds. Drag the order total and watch it choose.</p></div><div className={cx('iffy rv')}><div className={cx('slider')}><small className={cx('muted')}>A new order comes in for</small><output htmlFor="automation-order-total">${amount.toLocaleString('en-US')}</output><input type="range" id="automation-order-total" min="40" max="1200" step="10" value={amount} onChange={event => setAmount(Number(event.target.value))} aria-label="Order total" /></div><div className={cx('diag')}><RecipeNode cx={cx} item={{ color: 'teal', icon: 'zap', label: 'When', title: 'A new order arrives' }} /><div className={cx('q')}>IF order total is over $500</div><div className={cx('pair')}><div className={cx('path', big && 'live')}><RecipeNode cx={cx} item={{ color: 'amber', icon: 'user', label: 'Yes', title: 'Ask you to approve', detail: 'Pings your phone' }} /></div><div className={cx('path', !big && 'live')}><RecipeNode cx={cx} item={{ color: 'green', icon: 'mail', label: 'No', title: 'Confirm and email the customer', detail: 'Automatically' }} /></div></div><p className={cx('verdict')} aria-live="polite">{big ? 'Over $500, so it pauses and asks you before confirming.' : 'Under $500, so it confirms and emails the customer. No one had to lift a finger.'}</p></div></div></div></section>;
}
function Runs() {
  const reduced = useReducedMotion();
  const [runs, setRuns] = useState(initialRuns);
  const [selected, setSelected] = useState(0);
  const [testing, setTesting] = useState<number>();
  const nextId = useRef(4);
  const [gate, setGate] = useState<'draft' | 'warning' | 'fixed' | 'active' | 'paused'>('draft');
  const [fixed, setFixed] = useState(false);
  useEffect(() => {
    if (testing === undefined) return;
    const timer = setTimeout(() => {
      setRuns(previous => previous.map(run => run.id === testing ? { ...run, running: false, steps: [{ title: 'Find overdue invoices', io: 'Returned: 1 invoice' }, { title: 'Ask Invoice Chaser', io: 'Returned: 1 polite draft' }, { title: 'Send emails', io: 'Sent 1 of 1 (test mode)' }] } : run));
      setTesting(undefined);
    }, reduced ? 0 : 1800);
    return () => clearTimeout(timer);
  }, [testing, reduced]);
  const run = runs.find(item => item.id === selected) ?? runs[0];
  return <section><div className={cx('wrap')}><div className={cx('head trigger-head rv')}><span className={cx('chap eyebrow')}><b>5</b> Trust it</span><h2>See exactly what happened.<br />Nothing goes live untested.</h2><p className={cx('lead')}>Every run is recorded, step by step: what went in, what came out. And an automation can only go Active once every step checks out.</p></div><div className={cx('win rv')}><WindowBar cx={cx} title="Runs · Invoice reminders"><button type="button" className={cx('btn sm new-run')} disabled={testing !== undefined} onClick={() => { const id = nextId.current++; setRuns(previous => [{ id, name: 'Just now', passed: true, running: true, steps: [] }, ...previous]); setSelected(id); setTesting(id); }}><StoryIcon name="play" /> Run test</button></WindowBar><div className={cx('runs')}><div className={cx('rlist')}>{runs.map(item => <button type="button" key={item.id} aria-pressed={item.id === selected} className={cx('runrow', item.id === selected && 'on', !item.passed && 'bad', item.running && 'going')} onClick={() => setSelected(item.id)}><span className={cx('dot')} />{item.name}<small>{item.running ? 'running…' : item.passed ? 'Passed' : 'Failed'}</small></button>)}</div><div className={cx('rdetail')} aria-live="polite">{run.running ? <div className={cx('step-io')}><b><span className={cx('running')}>●</span> Running every step…</b></div> : run.steps.map(step => <div key={step.title} className={cx('step-io', step.failed && 'bad')}><b><span className={cx(step.failed ? 'failure' : 'success')}>{step.failed ? '✕' : '✓'}</span> {step.title}</b><pre>{step.io}</pre>{step.failed && <div className={cx('fix')}>Fix: add an email address to this customer, then run it again.</div>}</div>)}</div></div></div>
    <div className={cx('gate rv')}><div className={cx('row')}><button type="button" className={cx('sw', gate === 'active' && 'on')} aria-label="Activate automation" role="switch" aria-checked={gate === 'active'} onClick={() => setGate(gate === 'active' ? 'paused' : fixed ? 'active' : 'warning')} /><div><b>{gate === 'active' ? 'Active' : 'Draft'}</b><div className={cx('gate-subtitle')}>{gate === 'active' ? 'Next run: Monday 08:00' : gate === 'paused' ? 'Paused. Nothing will run on schedule.' : 'Try switching it on.'}</div></div>{gate === 'warning' && <button type="button" className={cx('btn ghost sm fix-button')} onClick={() => { setFixed(true); setGate('fixed'); }}>Fix it</button>}</div><div role="status" className={cx('msg', gate === 'warning' && 'warn', (gate === 'fixed' || gate === 'active') && 'ok')}>{gate === 'warning' ? <>⚠ <b>Needs attention.</b> The “Send emails” step has no subject. Nothing was switched on.</> : gate === 'fixed' ? '✓ Subject added: “Overdue invoices: {{ date }}”. Now try switching it on.' : gate === 'active' ? '✓ Every step checked. It will run on schedule from now on.' : ''}</div></div>
  </div></section>;
}
function Templates() {
  const [selected, setSelected] = useState<number>();
  const [name, setName] = useState('');
  const [agent, setAgent] = useState('Support Concierge');
  const [imported, setImported] = useState<Record<number, { name: string; agent: string }>>({});
  const [notice, setNotice] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const nameInput = useRef<HTMLInputElement>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(false), 3200);
    return () => clearTimeout(timer);
  }, [notice]);
  const close = () => { dialog.current?.close(); setSelected(undefined); opener.current?.focus(); };
  return <><section className={cx('band')}><div className={cx('wrap')}><div className={cx('head template-head rv')}><span className={cx('chap eyebrow')}><b>6</b> Start from a template</span><h2>Someone has already built it.<br />Import it in a click.</h2><p className={cx('lead')}>Pick one from the marketplace, choose which of your agents should do the work, and it lands as a draft, ready to test.</p></div><div className={cx('tpls')}>{templates.map((template, index) => <div key={template.name} className={cx('tpl')} style={nodeColor(template.color)}><div className={cx('ic')}><StoryIcon name={template.icon} /></div><b>{template.name}</b><p>{template.description}</p><div className={cx('meta')}><span>{template.meta}</span></div><button type="button" className={cx('btn sm', imported[index] ? 'green' : 'ghost')} onClick={event => { opener.current = event.currentTarget; setSelected(index); setName(template.name); dialog.current?.showModal(); nameInput.current?.focus(); }}>{imported[index] ? '✓ Imported as draft' : 'Import automation'}</button></div>)}</div></div></section>
    <dialog ref={dialog} className={cx('import-dialog')} aria-labelledby="automation-import-title" onCancel={event => { event.preventDefault(); close(); }} onClick={event => { if (event.target === event.currentTarget) { const bounds = event.currentTarget.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) close(); } }}><form className={cx('sheet')} onSubmit={event => { event.preventDefault(); if (selected === undefined) return; setImported(previous => ({ ...previous, [selected]: { name, agent } })); setNotice(true); close(); }}><h3 id="automation-import-title">Import{selected !== undefined ? ` “${templates[selected].name}”` : ''}</h3><div><label htmlFor="automation-import-name">Name</label><input ref={nameInput} id="automation-import-name" value={name} required onChange={event => setName(event.target.value)} /></div><div><label htmlFor="automation-import-agent">Which agent should do the work?</label><select id="automation-import-agent" value={agent} onChange={event => setAgent(event.target.value)}>{['Support Concierge', 'Booking Assistant', 'Lead Scout', 'Invoice Chaser'].map(value => <option key={value}>{value}</option>)}</select></div><div className={cx('import-actions')}><button type="submit" className={cx('btn green')}>Import as draft</button><button type="button" className={cx('btn ghost')} onClick={close}>Cancel</button></div></form></dialog><div className={cx('toastbar', notice && 'show')} role="status">{notice ? 'Imported. Add a trigger, run a test, then switch it on.' : ''}</div>
  </>;
}
function Outcome() {
  const { attach: demoRef, elapsed: demoElapsed } = useDemoClock(1400);
  const progress = 1 - Math.pow(1 - demoElapsed / 1400, 3);
  return <section id="start"><div className={cx('wrap')}><div className={cx('outcome-head rv')}><span className={cx('eyebrow')}>What it adds up to</span><h2>A week with automations<br />running in the background</h2></div><div className={cx('outs rv')} ref={demoRef}><div className={cx('out')}><b className={cx('grad')}>{Math.round(14 * progress)}</b><span>hours back, every week</span></div><div className={cx('out')}><b className={cx('grad')}>0</b><span>follow-ups forgotten</span></div><div className={cx('out')}><b className={cx('grad')}>{Math.round(100 * progress)}%</b><span>of runs recorded and reviewable</span></div></div><p className={cx('fine')}>Example numbers for a small bakery. Yours will differ.</p><div className={cx('outcome-gap')} /><div className={cx('final rv')}><h2>Pick one boring task.<br /><span className={cx('grad')}>Hand it to an agent tonight.</span></h2><p className={cx('lead centered')}>Start with a daily briefing. It takes about ten minutes, and tomorrow morning it is waiting for you.</p><div className={cx('cta')}><a className={cx('btn')} href="/login">Automate my first task, free</a><a className={cx('btn ghost')} href="/">Back to all features</a></div></div><NextFeatures cx={cx} items={[
    ['ila', 'sparkles', 'Ila', 'Let her build your automations'], ['agents', 'bot', 'Agents', 'The ones doing the work'], ['leads', 'inbox', 'Leads', 'What starts many automations'],
  ]} /></div></section>;
}
export function AutomationsPage() {
  return <StoryPage title="Automations — InnomightLabs" description="Your best employee never clocks out."><div className={cx('page')}><header className={cx('hero')}><div className={cx('wrap')}><div className={cx('intro')}><span className={cx('eyebrow')}>Automations</span><h1>Your best employee<br /><span className={cx('grad')}>never clocks out.</span></h1><p className={cx('lead')}>Tell your agents what to do and when. Invoices get chased, emails get sorted and your morning briefing is waiting, all while you sleep.</p><div className={cx('cta')}><a className={cx('btn')} href="#start">Automate my first task</a><a className={cx('btn ghost')} href="#say">See how it works</a></div></div><Night /></div></header><SayIt /><Builder /><Triggers /><Decisions /><Runs /><Templates /><Outcome /></div></StoryPage>;
}
