import type { ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../components/story/StoryPage', () => ({
  StoryPage: ({ children }: { children: ReactNode }) => <main>{children}</main>,
  StoryIcon: ({ name }: { name: string }) => <svg aria-hidden="true" data-icon={name} />,
  storyClasses: () => (...names: (string | false | undefined)[]) => names.filter(Boolean).join(' '),
}));
import { LandingPage } from './LandingPage';
import { HomeChat } from './homeDemos';

const renderPage = () => renderToStaticMarkup(<MemoryRouter><LandingPage /></MemoryRouter>);

describe('approved home story', () => {
  it('renders every chapter, supporting part, and final CTA without a duplicate shell', () => {
    const html = renderPage();
    for (const id of ['journey', 't-ila', 't-agents', 't-leads', 't-auto', 'start']) expect(html).toContain(`id="${id}"`);
    for (const copy of [
      'Meet Ila, your solution builder', 'by talking to it.', 'She picks the pieces.',
      'Add a layer, it gets smarter.', 'Without a single form.', 'never clocks out.',
      'Knowledge from your site', 'Skills: email, Drive, forms', 'Connectors for your tools',
      'Memory across chats', 'Chat widget for your site', 'Public API', 'Share with your team',
      'Kits you can undo', 'one conversation away.',
    ]) expect(html).toContain(copy);
    expect(html).not.toContain('<nav');
    expect(html).not.toContain('<footer');
    expect(html).not.toContain('<script');
    expect(html).not.toContain('class="note"');
  });

  it('routes every feature and CTA to real destinations', () => {
    const html = renderPage();
    for (const route of ['ila', 'agents', 'leads', 'automations']) expect(html).toContain(`href="/features/${route}"`);
    expect(html.match(/href="\/login"/g)).toHaveLength(2);
    expect(html.match(/href="\/pricing"/g)).toHaveLength(1);
    expect(html).toContain('href="#journey"');
    expect(html).not.toMatch(/href="(?:#|[^"]*\.html)"/);
    expect(html.match(/class="stop on?[^"]*"|class="stop"/g)).toHaveLength(4);
  });

  it('prelays every goal, message, plan, lead field, and overnight outcome', () => {
    const html = renderPage();
    for (const copy of [
      'Maple Concierge', 'Menu, prices, allergens', 'Captured in the chat', 'Morning summary',
      'Capture leads and follow up', 'A weekly report in my inbox', 'Weekly Digest',
      'New lead follow-up', 'Website chat', 'priya@example.com', 'June 14',
      'Inbox sorted', 'Late invoices nudged', 'Morning briefing in your inbox',
    ]) expect(html).toContain(copy);
    expect(html.match(/inert=""/g)).toHaveLength(2);
    expect(html.match(/answer-reserve/g)).toHaveLength(16);
    expect(html).toContain('class="tr"');
    expect(html).toContain('class="node pre"');
    expect(html).toContain('class="st">0 of 3');
  });

  it('uses native labelled controls with selected state for goals and layers', () => {
    const html = renderPage();
    expect(html.match(/<button type="button"/g)).toHaveLength(7);
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(2);
    expect(html.match(/aria-pressed="false"/g)).toHaveLength(5);
    expect(html).toContain('aria-controls="home-agent-answer"');
    for (let index = 0; index < 3; index++) expect(html).toContain(`aria-controls="home-goal-${index}"`);
  });

  it('shows a completed, non-thinking conversation for reduced motion', () => {
    const html = renderToStaticMarkup(<HomeChat lines={[[ 'u', 'Hello' ], [ 'a', 'Welcome!' ]]} elapsed={Infinity} />);
    expect(html).toContain('class="m u pre shown"');
    expect(html).toContain('class="m a pre shown said"');
    expect(html).not.toContain('thinking');
    expect(html).not.toContain('aria-hidden="true" class="m');
    expect(html).toContain('Hello');
    expect(html).toContain('Welcome!');
  });
});
