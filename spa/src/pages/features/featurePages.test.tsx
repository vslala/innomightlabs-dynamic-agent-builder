import type { ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AutomationsPage } from './AutomationsPage';
import { LeadsPage } from './LeadsPage';
import { DemoChat, Recipe } from './featureDemos';
import { chatDuration, type ChatLine } from './featureDemoTiming';

// These tests cover the page content and demo timelines; the parent owns shell integration.
vi.mock('../../components/story/StoryPage', () => ({
  StoryPage: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  StoryIcon: ({ name }: { name: string }) => <svg data-icon={name} />,
  storyClasses: (local: Record<string, string>) => (...names: (string | false | undefined)[]) => names.filter(Boolean).flatMap(name => String(name).split(/\s+/).map(token => local[token] ?? token)).join(' '),
}));
const clock = vi.hoisted(() => ({ elapsed: 0, reduced: false }));
vi.mock('./featureDemoTiming', async importOriginal => {
  const original = await importOriginal<typeof import('./featureDemoTiming')>();
  return { ...original, useReducedMotion: () => clock.reduced, useDemoClock: (duration: number) => ({ elapsed: clock.reduced ? duration : clock.elapsed, reduced: clock.reduced, attach: () => {}, replay: () => {} }) };
});
const cx = (...names: (string | false | undefined)[]) => names.filter(Boolean).join(' ');
const lines: ChatLine[] = [['u', 'Hello'], ['a', 'Welcome back']];
const render = (page: 'leads' | 'automations') => renderToStaticMarkup(<MemoryRouter>{page === 'leads' ? <LeadsPage /> : <AutomationsPage />}</MemoryRouter>);

describe('steady illustrative demos', () => {
  it('includes typing, thinking and exchange pauses in its timeline', () => {
    expect(chatDuration(lines)).toBe(990);
    expect(chatDuration(lines, 22, 250)).toBe(1510);
    expect(chatDuration(lines, 18, 0, 400)).toBe(1390);
  });
  it('preallocates complete chat text before revealing or typing it', () => {
    const initial = renderToStaticMarkup(<DemoChat lines={lines} elapsed={0} cx={cx} />);
    expect(initial).toContain('m u pre');
    expect(initial).toContain('<span class="tr">Hello</span>');
    expect(initial).toContain('<span class="tx">Welcome back</span>');
    const thinking = renderToStaticMarkup(<DemoChat lines={lines} elapsed={100} cx={cx} />);
    expect(thinking).toContain('m a pre shown thinking');
    const finished = renderToStaticMarkup(<DemoChat lines={lines} elapsed={990} cx={cx} />);
    expect(finished).toContain('m a pre shown said');
  });
  it('keeps recipe steps mounted while hidden, running and complete', () => {
    const nodes = [{ color: 'green', icon: 'mail', label: 'Then', title: 'Send summary' }];
    expect(renderToStaticMarkup(<Recipe nodes={nodes} cx={cx} elapsed={0} revealAt={500} runAt={1000} />)).toContain('class="node pre"');
    expect(renderToStaticMarkup(<Recipe nodes={nodes} cx={cx} elapsed={1000} revealAt={500} runAt={1000} />)).toContain('class="node pre shown run"');
    expect(renderToStaticMarkup(<Recipe nodes={nodes} cx={cx} elapsed={1750} revealAt={500} runAt={1000} />)).toContain('class="node pre shown ok"');
  });
});

describe('approved feature stories', () => {
  it('renders every leads chapter, configuration control, and real CTA', () => {
    clock.elapsed = 0; clock.reduced = false;
    const html = render('leads');
    for (const copy of ['Without a single form.', 'Why it works', 'You decide what matters', 'It remembers people', 'Straight into your day', 'Handled with care', 'Where it is going', 'chatting with you tonight.', 'Remove Name', 'Consent to contact', 'Select a lead to see its answers']) expect(html).toContain(copy);
    expect(html).toContain('href="/login"');
    expect(html).toContain('href="/features/automations"');
    expect(html).not.toContain('<script');
  });
  it('renders every automations chapter and all six import templates', () => {
    const html = render('automations');
    for (const copy of ['never clocks out.', 'Describe it', 'Build it your way', 'Start it any way', 'Let it decide', 'Trust it', 'Start from a template', 'What it adds up to', 'Supplier inbox triage', 'aria-label="Order total"', 'role="switch"', '<dialog']) {
      expect(html).toContain(copy);
    }
    expect(html.match(/>Import automation<\/button>/g)).toHaveLength(6);
    expect(html).toContain('href="/login"');
    expect(html).toContain('href="/features/leads"');
    expect(html).not.toContain('<script');
  });
  it('shows completed useful stories immediately with reduced motion', () => {
    clock.reduced = true;
    expect(render('leads')).toContain('Lead captured');
    const html = render('automations');
    expect(html).toContain('08:00');
    expect(html).toContain('You: ☕ awake, briefing ready');
    expect(html).toMatch(/>14<\/b>/);
    expect(html).toMatch(/>100%<\/b>/);
    clock.reduced = false;
  });
});
