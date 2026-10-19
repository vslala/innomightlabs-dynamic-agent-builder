import type { ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

// The shared shell is delivered separately; these tests cover only the ILA story.
vi.mock('../../components/story/StoryPage', () => ({
  StoryPage: ({ children }: { children: ReactNode }) => <main>{children}</main>,
  StoryIcon: ({ name }: { name: string }) => <svg aria-hidden="true" data-icon={name} />,
  storyClasses: () => (...names: (string | false | undefined)[]) => names.filter(Boolean).join(' '),
}));

import { IlaPage } from './IlaPage';

function renderPage() {
  return renderToStaticMarkup(<MemoryRouter><IlaPage /></MemoryRouter>);
}

describe('ILA feature story', () => {
  it('preserves every chapter and the final outcome', () => {
    const html = renderPage();
    for (const id of ['say', 'plan', 'kits', 'book', 'trust', 'start']) {
      expect(html).toContain(`id="${id}"`);
    }
    for (const copy of [
      'She builds it. You ship it.', 'Describe the outcome', 'Review before anything changes',
      'Never stuck with it', 'She knows the product', 'Built to be trusted',
      'Ila takes it from there.', 'Your own AI account',
    ]) expect(html).toContain(copy);
  });

  it('uses real signup and feature routes, with no mockup navigation', () => {
    const html = renderPage();
    expect(html.match(/href="\/login"/g)).toHaveLength(2);
    for (const route of ['/', '/features/agents', '/features/leads', '/features/automations']) {
      expect(html).toContain(`href="${route}"`);
    }
    expect(html).not.toMatch(/href="(?:#|[^"]*\.html)"/);
    expect(html).not.toContain('<script');
    expect(html).not.toContain('<footer');
  });

  it('lays out every goal, message, plan, and kit piece before animations begin', () => {
    const html = renderPage();
    for (const copy of [
      'Answer customers from my website', 'Capture leads and follow up', 'A weekly report in my inbox',
      'Answers with links to the source', 'New lead follow-up', 'Writes what moved and why',
      'Wedding enquiry', 'Morning summary', 'Kit removed. Everything it created is gone in one step.',
    ]) expect(html).toContain(copy);
    expect(html).toContain('class="m pre u shown"');
    expect(html).toContain('class="tr"');
    expect(html.match(/inert=""/g)).toHaveLength(3);
    expect(html).toContain('class="piece pre"');
  });

  it('starts with building, rollback, and rebuild safely gated', () => {
    const html = renderPage();
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Approve and build<\/button>/);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*><svg[^>]*data-icon="undo"[^>]*><\/svg>Roll back<\/button>/);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>↻ Rebuild<\/button>/);
    expect(html).toContain('aria-label="Kit version 1"');
    expect(html).toContain('aria-pressed="true"');
  });
});
