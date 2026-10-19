import { Fragment, useEffect, useRef, useState, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { StoryIcon, storyClasses } from '../components/story/StoryPage';
import styles from './LandingPage.module.css';
import {
  GOALS, HERO_CHAT, HERO_PLAN, HERO_TIMING, HOME_KINDS, HOME_LAYERS,
  LEAD_CAPTURE_AT, LEAD_CHAT, LEAD_CYCLE, LEAD_FIELDS, LEAD_STARTS, NIGHT, STOPS,
  conversationStarts, homeAnswer, messageDuration, nightState, startHomeClock,
  type HomeLayer, type HomeMessage, type HomePlanItem,
} from './homeDemo';

const cx = storyClasses(styles);
const color = (value: string) => ({ '--c': value }) as CSSProperties;

// All frames derive from one elapsed time; changing a demo cancels its old clock.
function useHomeTimeline(duration: number, loop = false, revision = 0) {
  const ref = useRef<HTMLDivElement>(null);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    let stopClock: (() => void) | undefined;
    let active = false;
    const begin = () => {
      if (stopClock) return;
      active = true;
      stopClock = startHomeClock({ duration, loop, reduced: () => media.matches, onElapsed: setElapsed });
    };
    const motionChanged = () => {
      stopClock?.();
      stopClock = undefined;
      if (active || media.matches) begin();
    };
    media.addEventListener('change', motionChanged);
    const observer = typeof IntersectionObserver === 'undefined' ? undefined : new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) {
        begin();
        observer?.disconnect();
      }
    }, { threshold: 0.15 });
    if (media.matches || !observer) begin();
    else if (ref.current) observer.observe(ref.current);
    return () => {
      stopClock?.();
      observer?.disconnect();
      media.removeEventListener('change', motionChanged);
    };
  }, [duration, loop, revision]);
  return { ref, elapsed, reset: () => setElapsed(0) };
}

function WindowBar({ title }: { title: string }) {
  return <div className={cx('bar')}><i /><i /><i /><span>{title}</span></div>;
}

export function HomeChat({ lines, elapsed, starts = conversationStarts(lines), speeds = [] }: {
  lines: readonly HomeMessage[]; elapsed: number; starts?: readonly number[]; speeds?: readonly number[];
}) {
  return <div className={cx('msgs')} aria-label="Illustrative conversation">{lines.map((line, index) => {
    const [who, text] = line;
    const speed = speeds[index] ?? 18;
    const shown = elapsed >= starts[index];
    const said = elapsed >= starts[index] + messageDuration(line, speed);
    const count = Math.max(0, Math.min(text.length, Math.floor((elapsed - starts[index]) / speed)));
    return <div key={index} aria-hidden={!shown || (who === 'a' && !said)} className={cx('m', who, 'pre', shown && 'shown', who === 'a' && said && 'said', who === 'a' && shown && !said && 'thinking')}>
      {who === 'u' ? <><span className={cx('tp')}>{text.slice(0, count)}</span><span className={cx('tr')} aria-hidden="true">{text.slice(count)}</span></> : <><span className={cx('tx')}>{text}</span><span className={cx('th dots')} aria-hidden="true"><i /><i /><i /></span></>}
    </div>;
  })}</div>;
}

function HomePlan({ items, elapsed, revealAt, step = 400, runAt = Infinity }: {
  items: readonly HomePlanItem[]; elapsed: number; revealAt: number; step?: number; runAt?: number;
}) {
  return <div className={cx('plan')}><div className={cx('chain')}>{items.map(([kind, title, detail], index) => {
    const [icon, tint, label] = HOME_KINDS[kind];
    const visible = elapsed >= revealAt + index * step;
    const running = Number.isFinite(runAt) && elapsed >= runAt + index * 600 && elapsed < runAt + (index + 1) * 600;
    const done = Number.isFinite(runAt) && elapsed >= runAt + (index + 1) * 600;
    return <Fragment key={title}>{index > 0 && <div className={cx('link pre', visible && 'shown')} aria-hidden="true" />}<div style={color(tint)} aria-hidden={!visible} className={cx('node pre', visible && 'shown', running && 'run', done && 'ok')}>
      <div className={cx('ic')}><StoryIcon name={icon} /></div><div className={cx('t')}><small>{label}</small><b>{title}</b><span>{detail}</span></div><div className={cx('st')} aria-hidden="true">✓</div>
    </div></Fragment>;
  })}</div></div>;
}

export function HomeHeroDemo() {
  const { ref, elapsed } = useHomeTimeline(HERO_TIMING.cycle, true);
  return <div ref={ref} className={cx('win rv')}><WindowBar title="Ila · Maple & Co. Bakery" /><div className={cx('build')}>
    <div className={cx('chatcol')}><HomeChat lines={HERO_CHAT} elapsed={elapsed} starts={HERO_TIMING.starts} speeds={[20, 18, 18, 18]} /></div>
    <div className={cx('plancol')}><div className={cx('plan-h')}><StoryIcon name="layers" />Plan <span className={cx('ver', elapsed >= HERO_TIMING.builtAt && 'on')} aria-hidden={elapsed < HERO_TIMING.builtAt}>Built · Kit v1</span></div><HomePlan items={HERO_PLAN} elapsed={elapsed} revealAt={HERO_TIMING.planAt} runAt={HERO_TIMING.runAt} /></div>
  </div></div>;
}

export function HomeJourney() {
  const { ref, elapsed } = useHomeTimeline(10400, true);
  const [selected, setSelected] = useState<number>();
  const step = selected ?? (elapsed === Infinity ? 3 : Math.floor(elapsed / 2600));
  const current = STOPS[step];
  return <><div ref={ref} className={cx('journey rv')}>{STOPS.map(([feature, href, tint, emoji, title, detail, , more], index) => <Link key={title} to={href} className={cx('stop', index <= step && 'on')} style={color(tint)} onMouseEnter={() => setSelected(index)} onFocus={() => setSelected(index)}>
    <div className={cx('n')}><i aria-hidden="true">{emoji}</i>{feature}</div><b>{title}</b><p>{detail}</p><span className={cx('go')}>{more} <StoryIcon name="right" /></span>
  </Link>)}</div><div className={cx('logline')}><b>{current[8]}</b> · {current[6]}</div></>;
}

export function HomeGoals() {
  const [goal, setGoal] = useState(0);
  const [revision, setRevision] = useState(0);
  const { ref, elapsed, reset } = useHomeTimeline(5000, false, revision);
  return <div className={cx('wrap split')}><div className={cx('rv')}><span className={cx('chap eyebrow')}><b>1</b> Ila</span><h2>Say the goal.<br />She picks the pieces.</h2>
    <p className={cx('lead')}>Ila chooses from everything InnomightLabs offers, shows you a plan, and builds it as one kit you can change or undo.</p>
    <div className={cx('goals')}>{GOALS.map(({ label }, index) => <button key={label} type="button" className={cx('chipbtn', index === goal && 'on')} aria-pressed={index === goal} aria-controls={`home-goal-${index}`} onClick={() => { setGoal(index); setRevision(value => value + 1); reset(); }}>{label}</button>)}</div>
    <Link className={cx('more')} to="/features/ila">Meet Ila <StoryIcon name="right" /></Link></div>
    <div ref={ref} className={cx('win rv')}><WindowBar title="Ila" /><div className={cx('pad')}><div className={cx('stack')}>{GOALS.map(({ question, plan }, index) => {
      const lines: readonly HomeMessage[] = [['u', question], ['a', 'I would build this:']];
      const starts = conversationStarts(lines, 14, 0);
      return <div key={question} id={`home-goal-${index}`} className={cx('goal-panel', index === goal && 'on')} aria-hidden={index !== goal} inert={index !== goal}>
        <div className={cx('goal-chat')}><HomeChat lines={lines} elapsed={index === goal ? elapsed : 0} starts={starts} speeds={[14, 14]} /></div>
        <HomePlan items={plan} elapsed={index === goal ? elapsed : 0} revealAt={starts[1] + 900} step={350} />
      </div>;
    })}</div></div></div></div>;
}

const ANSWER_VARIANTS = Array.from({ length: 16 }, (_, mask) => {
  const layers = new Set(HOME_LAYERS.filter((_, index) => mask & (1 << index)).map(([key]) => key));
  return { text: homeAnswer(layers), source: layers.has('knowledge') };
});
function Source() {
  return <span className={cx('src')}><StoryIcon name="link" />maplebakery.com/menu</span>;
}
export function HomeAgents() {
  const [layers, setLayers] = useState<ReadonlySet<HomeLayer>>(new Set(['knowledge']));
  const [revision, setRevision] = useState(0);
  const { ref, elapsed, reset } = useHomeTimeline(4000, false, revision);
  const answer = homeAnswer(layers);
  const count = Math.min(answer.length, Math.floor(elapsed / 11));
  return <div className={cx('wrap split rev')}><div className={cx('rv')}><span className={cx('chap eyebrow')}><b>2</b> Agents</span><h2>Same agent.<br />Add a layer, it gets smarter.</h2>
    <p className={cx('lead')}>Give an agent your knowledge, your tools and a memory, and it stops sounding like a chatbot and starts working like your best employee.</p>
    <div className={cx('layers')}>{HOME_LAYERS.map(([key, icon, tint, title, detail]) => <button type="button" key={key} className={cx('layer', layers.has(key) && 'on')} style={color(tint)} aria-pressed={layers.has(key)} aria-controls="home-agent-answer" onClick={() => {
      setLayers(current => { const next = new Set(current); if (next.has(key)) next.delete(key); else next.add(key); return next; });
      setRevision(value => value + 1); reset();
    }}><span className={cx('ic')}><StoryIcon name={icon} /></span><span><b>{title}</b><small>{detail}</small></span><span className={cx('sw')} aria-hidden="true" /></button>)}</div>
    <Link className={cx('more')} to="/features/agents">Explore agents <StoryIcon name="right" /></Link></div>
    <div ref={ref} className={cx('win rv')}><WindowBar title="Maple Concierge" /><div className={cx('pad')}><div className={cx('msgs')}><div className={cx('m u full-message')}>Do you have gluten free options? I need something for Saturday.</div>
      <div className={cx('stack')}>{ANSWER_VARIANTS.map(({ text, source }) => <div key={text} className={cx('m a full-message answer-reserve')} aria-hidden="true">{text}{source && <Source />}</div>)}
        <div className={cx('m a full-message answer on')} id="home-agent-answer" aria-label={answer}><span className={cx('answer-text')}>{answer.slice(0, count)}</span><span className={cx('answer-rest')} aria-hidden="true">{answer.slice(count)}</span>{layers.has('knowledge') && <span className={cx(count < answer.length && 'answer-rest')}><Source /></span>}</div>
      </div></div></div></div></div>;
}

export function HomeLeadsDemo() {
  const { ref, elapsed } = useHomeTimeline(LEAD_CYCLE, true);
  const captured = LEAD_CAPTURE_AT.filter(time => elapsed >= time).length;
  return <div ref={ref} className={cx('win rv')}><WindowBar title="maplebakery.com" /><div className={cx('duo')}>
    <div className={cx('chatcol')}><HomeChat lines={LEAD_CHAT} elapsed={elapsed} starts={LEAD_STARTS} /></div>
    <div className={cx('leadcol')}><div className={cx('lead-h')}>Wedding enquiry <span className={cx('st', captured === 3 && 'done')}>{captured === 3 ? 'Lead captured' : `${captured} of 3`}</span></div><div className={cx('fields')}>
      {LEAD_FIELDS.map(([label, value], index) => <div key={label} className={cx('field', index < captured && 'got')}><small>{label}</small><b aria-hidden={index >= captured}>{value}</b><span className={cx('ck')} aria-hidden="true">✓</span></div>)}
    </div></div></div></div>;
}

export function HomeNightDemo() {
  const { ref, elapsed } = useHomeTimeline(16000, true);
  const state = nightState(elapsed);
  return <div ref={ref} className={cx('win rv')}><div className={cx('sky')}><div className={cx('orb')} style={{ left: `calc(14px + (100% - 28px) * ${state.progress})` }} aria-hidden="true">{state.orb}</div><div className={cx('who')}>{state.who}</div><div className={cx('clock')}>{state.clock}</div><div className={cx('track')}><div className={cx('fill')} style={{ width: `${state.progress * 100}%` }} /></div></div>
    <ul className={cx('done-list')}>{NIGHT.map(item => <li key={item.name} style={color(item.color)} className={cx(state.minute >= item.minute && 'on')}><div className={cx('ic')}><StoryIcon name={item.icon} /></div>{item.name}<time>{item.at}</time></li>)}</ul>
  </div>;
}
