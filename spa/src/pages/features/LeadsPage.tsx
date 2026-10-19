import { Fragment, useState } from 'react';
import { StoryPage, StoryIcon, storyClasses } from '../../components/story/StoryPage';
import { DemoChat, NextFeatures, Recipe, WindowBar, type DemoNode } from './featureDemos';
import { chatDuration, nodeColor, useDemoClock, type ChatLine } from './featureDemoTiming';
import styles from './LeadsPage.module.css';

const cx = storyClasses(styles);
const fields = [['Name', 'Priya'], ['Need', 'Wedding cake, 80 guests'], ['Date', 'Saturday, June 14'], ['Email', 'priya@example.com'], ['Budget', '$800 to $1,200']];
const script: ChatLine[] = [
  ['u', 'Hi! I am looking for a cake for my wedding.'], ['a', 'Congratulations! I would love to help. What is your name?'],
  ['u', 'I am Priya. About 80 guests.'], ['a', 'Lovely to meet you, Priya. 80 guests is a great size. What is the date?'],
  ['u', 'June 14th, a Saturday.'], ['a', 'June 14 is open. What budget should I plan around?'],
  ['u', 'Around $800 to $1,200.'], ['a', 'Perfect. Where shall I send the tasting invite and quote?'],
  ['u', 'priya@example.com'], ['a', 'Done. You will hear from us within the hour, Priya.'],
];
const conversation: ChatLine[] = [['u', 'Hi! Looking for a wedding cake.'], ['a', 'Congratulations! What is the date?'], ['u', 'June 14th.'], ['a', 'It is open. About how many guests?'], ['u', 'Around 80.'], ['a', 'Perfect. What is the best email for a quote?']];
const formFields = ['Full name', 'Email', 'Phone', 'Company', 'Event date', 'Guest count', 'Budget', 'How did you hear about us?'];
const pool = {
  name: { label: 'Name', detail: 'Who is it?', required: true },
  email: { label: 'Email', detail: 'To send the quote', required: true },
  need: { label: 'What they need', detail: 'In their own words', required: true },
  date: { label: 'Event date', detail: '', required: false },
  budget: { label: 'Budget range', detail: '', required: false },
  phone: { label: 'Phone', detail: '', required: false },
  company: { label: 'Company', detail: '', required: false },
  consent: { label: 'Consent to contact', detail: 'A required tick, stored with the lead', required: true },
};
type FieldKey = keyof typeof pool;
type LeadStatus = 'new' | 'contacted' | 'won';
type Lead = { name: string; need: string; agent: string; status: LeadStatus; date: string; budget: string; email: string };
const initialLeads: Lead[] = [
  { name: 'Sam R.', need: 'Retirement party cake · 40 guests', agent: 'Catering Concierge', status: 'won', date: 'May 12', budget: '$300', email: 'sam@example.com' },
  { name: 'Priya S.', need: 'Wedding cake · 80 guests', agent: 'Wedding Greeter', status: 'new', date: 'June 14', budget: '$800 to $1,200', email: 'priya@example.com' },
  { name: 'Tom H.', need: 'Corporate lunch · 25 people', agent: 'Catering Concierge', status: 'contacted', date: 'July 2', budget: '$600', email: 'tom@harbour.co' },
  { name: 'Aisha K.', need: 'Birthday cake · 12 guests', agent: 'Wedding Greeter', status: 'won', date: 'May 30', budget: '$150', email: 'aisha@example.com' },
];
const incoming: Lead[] = [
  { name: 'Marco D.', need: 'Anniversary dessert table', agent: 'Wedding Greeter', status: 'new', date: 'Aug 9', budget: '$400', email: 'marco@example.com' },
  { name: 'Lena V.', need: 'Cafe wholesale order', agent: 'Catering Concierge', status: 'new', date: 'ongoing', budget: '$2,000/mo', email: 'lena@cafe.co' },
];
const flow: DemoNode[] = [
  { color: 'pink', icon: 'inbox', label: 'When', title: 'A lead is captured', detail: 'Wedding enquiry' },
  { color: 'green', icon: 'search', label: 'Then', title: 'Ask Lead Scout to research', detail: 'Who are they, what do they like' },
  { color: 'gradient-start', icon: 'mail', label: 'Then', title: 'Email you the summary' },
  { color: 'purple', icon: 'plug', label: 'Then', title: 'Add to your CRM', detail: 'Through your connected tool' },
];
const visits = [
  { title: 'Monday · first visit', color: 'gradient-start', message: '“Hi, I am planning a wedding.”', memory: ['Name: Priya', 'Need: wedding cake'] },
  { title: 'Thursday · she is back', color: 'purple', message: 'Agent: “Welcome back, Priya! Have you picked a date?”', memory: ['Date: June 14', 'Guests: 80'] },
  { title: 'Saturday · third visit', color: 'green', message: 'Agent: “Where shall I send the quote?”', memory: ['Email: priya@example.com', '✓ Lead captured'] },
];

function LeadHero() {
  const duration = chatDuration(script, 18, 0, 400);
  const { attach: demoRef, elapsed: demoElapsed, reduced: demoReduced, replay: replayDemo } = useDemoClock(duration + 6500, true);
  const elapsed = demoReduced ? duration : demoElapsed;
  const captured = elapsed >= duration;
  const collected = [0, 1, 2, 4, 3].filter((_, index) => elapsed >= chatDuration(script.slice(0, index * 2 + 2)) + index * 400);

  return <header className={cx('hero')}><div className={cx('wrap')}>
    <div className={cx('intro')}><span className={cx('eyebrow')}>Leads</span><h1>Turn visitors into leads.<br /><span className={cx('grad')}>Without a single form.</span></h1><p className={cx('lead')}>Your agent chats with every visitor, learns who they are over time, and saves a complete lead the moment it has what you need. Then your automations take it from there.</p><div className={cx('cta')}><a className={cx('btn')} href="#start">Start capturing leads</a><button type="button" className={cx('btn ghost')} onClick={replayDemo}>↻ Watch again</button></div></div>
    <div className={cx('win rv')} ref={demoRef}><WindowBar cx={cx} title="Maple & Co. · maplebakery.com" /><div className={cx('duo')}>
      <div className={cx('chatcol')}><div className={cx('vis')}><i>P</i> A visitor on your website</div><DemoChat lines={script} elapsed={elapsed} cx={cx} exchangePause={400} /></div>
      <div className={cx('leadcol')}><div className={cx('lead-h')}><StoryIcon name="inbox" />Wedding enquiry <span className={cx('st', captured && 'done')}>{captured ? 'Lead captured' : `${collected.length} of 5 known`}</span></div><div className={cx('fields')}>{fields.map(([label, value], index) => <div key={label} className={cx('field', collected.includes(index) && 'got', collected.includes(index) && 'flash')}><small>{label}</small><b>{value}</b><span className={cx('ck')} aria-hidden="true">✓</span></div>)}</div><div className={cx('ping pre', captured && 'shown')}><StoryIcon name="mail" /><div><b>New lead: Priya, wedding cake</b><br /><small className={cx('muted')}>Emailed to you and added to your list</small></div></div></div>
    </div></div>
  </div></header>;
}
function FormComparison() {
  const { attach: demoRef, elapsed: demoElapsed } = useDemoClock(chatDuration(conversation, 22, 250));
  return <div ref={demoRef} className={cx('vs rv')}>
    <div className={cx('pane2')}><h3>A form</h3><small>Eight fields before they get anything</small><div className={cx('ff')}>{formFields.map((field, index) => <div key={field} className={cx(index < 3 && demoElapsed >= (index + 1) * 900 && 'fill', (index < 3 ? demoElapsed >= index * 900 && demoElapsed < (index + 1) * 900 : index === 3 && demoElapsed >= 2700) && 'cur')}>{field}</div>)}</div><div className={cx('verdict bad pre', demoElapsed >= 2700 && 'shown')}>Left at field 3. No lead.</div></div>
    <div className={cx('pane2')}><h3>A conversation</h3><small>One easy question at a time</small><DemoChat lines={conversation} elapsed={demoElapsed} cx={cx} speed={22} pause={250} /><div className={cx('verdict good pre', demoElapsed >= chatDuration(conversation, 22, 250) && 'shown')}>Lead captured, and they got a quote idea too.</div></div>
  </div>;
}
function LeadFields() {
  const [have, setHave] = useState<[FieldKey, boolean][]>([['name', true], ['email', true], ['need', true], ['budget', false]]);
  const required = have.filter(([, value]) => value).map(([key]) => pool[key].label.toLowerCase());
  const optional = have.filter(([, value]) => !value).map(([key]) => pool[key].label.toLowerCase());
  return <section className={cx('band')} id="choose"><div className={cx('wrap split rev')}><div className={cx('rv')}><span className={cx('chap eyebrow')}><b>2</b> You decide what matters</span><h2>Pick what to collect.<br />The agent works out how to ask.</h2><p className={cx('lead')}>Define a lead form once: the fields, which are required, and a consent line. Your agent knows exactly what it needs and when the lead is complete. Add or remove fields to see how it changes.</p><div className={cx('adds')}><span className={cx('add-label')}>Add:</span>{(Object.keys(pool) as FieldKey[]).filter(key => !have.some(([present]) => key === present)).map(key => <button type="button" key={key} className={cx('chipbtn')} onClick={() => setHave(previous => [...previous, [key, pool[key].required]])}><StoryIcon name="plus" />{pool[key].label}</button>)}</div></div>
    <div className={cx('win rv')}><WindowBar title="Lead form · Wedding enquiry" cx={cx} /><div className={cx('pad')}><div className={cx('ed')}>{have.map(([key, required]) => <div className={cx('fld')} key={key}><div><b>{pool[key].label}</b>{pool[key].detail && <small>{pool[key].detail}</small>}</div><button type="button" className={cx('req', required && 'on')} aria-label={`${pool[key].label}: ${required ? 'required' : 'optional'}`} aria-pressed={required} onClick={() => setHave(previous => previous.map(([field, value]) => [field, field === key ? !value : value]))}>{required ? 'Required' : 'Optional'}</button><button type="button" className={cx('x')} aria-label={`Remove ${pool[key].label}`} onClick={() => setHave(previous => previous.filter(([field]) => field !== key))}><StoryIcon name="x" /></button></div>)}</div><div className={cx('askbox')} aria-live="polite"><b>The agent now knows</b><ul><li>The lead is <b>complete</b> once it has: {required.join(', ') || 'nothing yet'}.</li>{optional.length > 0 && <li>Will ask for, but not insist on: {optional.join(', ')}.</li>}{have.some(([key]) => key === 'consent') && <li>Will not save without consent.</li>}</ul></div></div></div>
  </div></section>;
}
function ReturningVisits() {
  const { attach: demoRef, elapsed: demoElapsed } = useDemoClock(3300);
  return <div className={cx('visits')} ref={demoRef}>{visits.map((visit, index) => <div key={visit.title} style={nodeColor(visit.color)} className={cx('visit', index === 2 && 'final', demoElapsed > index * 1100 && 'on')}><h4><StoryIcon name="clock" />{visit.title}</h4><div className={cx('m')}>{visit.message}</div><div className={cx('mem')}>{visit.memory.map(memory => <span key={memory}>{memory}</span>)}</div></div>)}</div>;
}
function Captures() {
  const { attach: demoRef, elapsed: demoElapsed, reduced: demoReduced } = useDemoClock(11200);
  const [agent, setAgent] = useState('All');
  const [selected, setSelected] = useState<string>();
  const [statuses, setStatuses] = useState<Record<string, LeadStatus>>({});
  const [conversationOpen, setConversationOpen] = useState(false);
  const count = demoReduced ? 0 : Math.min(2, Math.floor(demoElapsed / 4000));
  const leads = [...incoming.slice(0, count).reverse(), ...initialLeads].filter(lead => agent === 'All' || lead.agent === agent).slice(0, 4);
  const lead = leads.find(item => item.name === selected);
  return <div className={cx('win rv')} ref={demoRef}><WindowBar cx={cx} title="Leads · Captures" /><div className={cx('pad')}><div className={cx('filters')}><span className={cx('filter-label')}>Agent</span>{['All', 'Wedding Greeter', 'Catering Concierge'].map(value => <button type="button" key={value} className={cx('chipbtn', agent === value && 'on')} aria-pressed={agent === value} onClick={() => { setAgent(value); setConversationOpen(false); }}>{value}</button>)}</div><div className={cx('tbl')}>{leads.map(item => { const status = statuses[item.name] ?? item.status; return <button type="button" key={item.name} className={cx('lr', item.name === selected && 'sel')} aria-pressed={item.name === selected} onClick={() => { setSelected(item.name); setConversationOpen(false); }}><b>{item.name}</b><small>{item.need} · {item.agent}</small><span className={cx('badge', status)}>{status[0].toUpperCase() + status.slice(1)}</span></button>; })}</div>
    <div className={cx('detail stack')}><div className={cx(!!lead && 'on')}>{lead && <><dl>{[['Name', lead.name], ['Need', lead.need], ['Date', lead.date], ['Budget', lead.budget], ['Email', lead.email]].map(([label, value]) => <Fragment key={label}><dt>{label}</dt><dd>{value}</dd></Fragment>)}<dt>Chat</dt><dd><button type="button" className={cx('conversation-link')} aria-expanded={conversationOpen} onClick={() => setConversationOpen(value => !value)}>Open the conversation →</button></dd></dl><select aria-label="Status" value={statuses[lead.name] ?? lead.status} onChange={event => setStatuses(previous => ({ ...previous, [lead.name]: event.target.value as LeadStatus }))}>{(['new', 'contacted', 'won'] as const).map(status => <option value={status} key={status}>{status[0].toUpperCase() + status.slice(1)}</option>)}</select></>}</div><div className={cx('none', !lead && 'on')}>Select a lead to see its answers and the conversation behind it.</div></div>
    {conversationOpen && lead && <div className={cx('conversation-preview')} role="region" aria-label="Illustrative lead conversation"><b>{lead.name} · Example conversation</b><p>Visitor: I am interested in {lead.need.toLowerCase()}.</p><p>Agent: Thank you! We will send the details to {lead.email}.</p></div>}
  </div><div role="status" className={cx('toastbar', count > 0 && demoElapsed < count * 4000 + 3200 && 'show')}>{count > 0 ? 'New lead captured' : ''}</div></div>;
}

export function LeadsPage() {
  return <StoryPage title="Leads — InnomightLabs" description="Turn visitors into leads. Without a single form."><div className={cx('page')}>
    <LeadHero />
    <section id="vs"><div className={cx('wrap')}><div className={cx('head rv')}><span className={cx('chap eyebrow')}><b>1</b> Why it works</span><h2>Nobody likes forms.<br />Everybody likes being helped.</h2><p className={cx('lead')}>A long form asks everything up front and gets nothing back from the visitor. A conversation asks one easy thing at a time, and answers questions along the way.</p></div><FormComparison /></div></section>
    <LeadFields />
    <section id="time"><div className={cx('wrap')}><div className={cx('head rv')}><span className={cx('chap eyebrow')}><b>3</b> It remembers people</span><h2>It does not interrogate.<br />It gets to know them.</h2><p className={cx('lead')}>Visitors come back. Your agent remembers what they already said, so it only asks for what is missing. The lead is saved the moment it is complete.</p></div><ReturningVisits /></div></section>
    <section className={cx('band')} id="tools"><div className={cx('wrap split')}><div className={cx('rv')}><span className={cx('chap eyebrow')}><b>4</b> Straight into your day</span><h2>A new lead starts the work.<br />You just see the result.</h2><p className={cx('lead')}>Every captured lead can start an automation: research the company, email you, add it to your CRM. Everything lands in one list with its status, the answers and the conversation behind it.</p><Recipe nodes={flow} cx={cx} /></div><Captures /></div></section>
    <section id="trust"><div className={cx('wrap')}><div className={cx('head rv')}><span className={cx('chap eyebrow')}><b>5</b> Handled with care</span><h2>Visitors trust you with<br />their details. Keep it that way.</h2></div><div className={cx('trust rv')}>{[['check', 'Consent first', 'A form with a consent line cannot be saved without it.'], ['lock', 'Only your team sees leads', "Access follows your team permissions. Visitors never see anyone's details."], ['shield', 'The agent cannot be tricked', 'Which account, agent and form a lead belongs to comes from the system, never from what a visitor types.']].map(([icon, title, description]) => <div key={title} className={cx('tc')}><div className={cx('ic')}><StoryIcon name={icon} /></div><b>{title}</b><p>{description}</p></div>)}</div></div></section>
    <section className={cx('band')} id="next"><div className={cx('wrap')}><div className={cx('head rv')}><span className={cx('chap eyebrow')}><b>6</b> Where it is going</span><h2>From a list of leads<br />to a pipeline.</h2></div><div className={cx('road rv')}>{[['One person, one record', 'Several captures from the same visitor merge into one contact with their whole history.'], ['A board for your team', 'Notes, tags, owners and a pipeline view, plus export.'], ['Agents that qualify', 'The agent scores a lead from the conversation and follows up when it said it would.']].map(([title, description]) => <div key={title} className={cx('rd')}><em>Coming</em><b>{title}</b><p>{description}</p></div>)}</div></div></section>
    <section id="start"><div className={cx('wrap')}><div className={cx('final rv')}><h2>Your next customer is<br /><span className={cx('grad')}>chatting with you tonight.</span></h2><p className={cx('lead centered')}>Put an agent on your website, tell it what you need to know, and let it do the asking.</p><div className={cx('cta')}><a className={cx('btn')} href="/login">Start capturing leads, free</a><a className={cx('btn ghost')} href="/">Back to all features</a></div></div><NextFeatures cx={cx} items={[
      ['agents', 'bot', 'Agents', 'The ones that do the chatting'], ['automations', 'clock', 'Automations', 'What happens after a lead'], ['ila', 'sparkles', 'Ila', 'Build all of this in one chat'],
    ]} /></div></section>
  </div></StoryPage>;
}
