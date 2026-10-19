import { Fragment, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { chatDuration, nodeColor, type ChatLine } from './featureDemoTiming';
import { StoryIcon } from '../../components/story/StoryPage';

type Classes = (...names: (string | false | undefined)[]) => string;
export function DemoChat({ lines, elapsed, cx, speed = 18, pause = 0, exchangePause = 0 }: { lines: readonly ChatLine[]; elapsed: number; cx: Classes; speed?: number; pause?: number; exchangePause?: number }) {
  return <div className={cx('msgs')} aria-label="Illustrative conversation">{lines.map(([who, text], index) => {
    const start = chatDuration(lines.slice(0, index), speed, pause, exchangePause);
    const duration = who === 'u' ? text.length * speed : 900;
    const shown = elapsed > start;
    const said = elapsed >= start + duration;
    const count = Math.max(0, Math.min(text.length, Math.floor((elapsed - start) / speed)));
    return <div key={index} className={cx('m', who, 'pre', shown && 'shown', who === 'a' && !said && shown && 'thinking', who === 'a' && said && 'said')}>
      {who === 'u' ? <><span className={cx('tp')}>{text.slice(0, count)}</span><span className={cx('tr')}>{text.slice(count)}</span></> : <><span className={cx('tx')}>{text}</span><span className={cx('th dots')} aria-hidden="true"><i /><i /><i /></span></>}
    </div>;
  })}</div>;
}

export type DemoNode = { color: string; icon: string; label: string; title: string; detail?: ReactNode };
export function RecipeNode({ item, cx, className, children, remove }: { item: DemoNode; cx: Classes; className?: string; children?: ReactNode; remove?: () => void }) {
  return <div className={[cx('node'), className].filter(Boolean).join(' ')} style={nodeColor(item.color)}><div className={cx('ic')}><StoryIcon name={item.icon} /></div><div className={cx('t')}><small>{item.label}</small><b>{item.title}</b>{item.detail && <span>{item.detail}</span>}{children}</div>{remove ? <button type="button" className={cx('x')} onClick={remove} aria-label={`Remove ${item.title}`}><StoryIcon name="x" /></button> : <div className={cx('st')} aria-hidden="true">✓</div>}</div>;
}
export function Recipe({ nodes, cx, elapsed, revealAt = 0, runAt = Infinity, stepMs = 750 }: { nodes: DemoNode[]; cx: Classes; elapsed?: number; revealAt?: number; runAt?: number; stepMs?: number }) {
  return <div className={cx('chain')}>{nodes.map((item, index) => {
    const visible = elapsed === undefined || elapsed >= revealAt + index * 520;
    const running = elapsed !== undefined && elapsed >= runAt + index * stepMs && elapsed < runAt + (index + 1) * stepMs;
    const done = elapsed !== undefined && elapsed >= runAt + (index + 1) * stepMs;
    return <Fragment key={index}>{index > 0 && <div className={cx('link', elapsed !== undefined && 'pre', visible && 'shown')} />}<RecipeNode item={item} cx={cx} className={cx(elapsed !== undefined && 'pre', visible && 'shown', running && 'run', done && 'ok')} /></Fragment>;
  })}</div>;
}
export function WindowBar({ title, cx, children }: { title: string; cx: Classes; children?: ReactNode }) {
  return <div className={cx('bar')}><i /><i /><i /><span>{title}</span>{children}</div>;
}
export function NextFeatures({ items, cx }: { items: readonly (readonly [string, string, string, string])[]; cx: Classes }) {
  return <div className={cx('next')}>{items.map(([route, icon, title, detail]) => <Link key={route} to={`/features/${route}`}><span className={cx('ic')}><StoryIcon name={icon} /></span><div><b>{title}</b><small>{detail}</small></div><span className={cx('go')}><StoryIcon name="right" /></span></Link>)}</div>;
}
