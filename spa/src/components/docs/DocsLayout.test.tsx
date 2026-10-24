import type { ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { DocsLayout } from './DocsLayout';
import { QuickStart } from '../../pages/docs/QuickStart';
import { PublicApi } from '../../pages/docs/PublicApi';
import { AgentToAgent } from '../../pages/docs/AgentToAgent';
import { Automations } from '../../pages/docs/Automations';
import { FAQ } from '../../pages/docs/FAQ';

// Keep public chrome and the interactive tutorial out of the shell's SSR tests.
vi.mock('../Navbar', () => ({ Navbar: () => <header>Site navigation</header> }));
vi.mock('../Footer', () => ({ Footer: () => <footer>Site footer</footer> }));
vi.mock('../../pages/docs/automations/AutomationSandbox', () => ({
  AutomationSandbox: () => <div data-docs-embed="">Automation tutorial</div>,
}));

const navItems = [
  { id: 'overview', label: 'Overview', href: '#overview' },
  { id: 'setup', label: 'Setup & configuration', href: '#setup' },
  { id: 'examples', label: 'Examples', href: '#examples' },
];
const docsLinks = [
  { href: '/docs/quick-start', label: 'Quick Start' },
  { href: '/docs/automations', label: 'Automations' },
  { href: '/docs/agent-to-agent', label: 'Agent2Agent' },
  { href: '/docs/public-api', label: 'Public API' },
  { href: '/docs/faq', label: 'FAQ' },
  { href: '/whats-new', label: 'What&#x27;s New' },
];

function render(content: ReactNode, path = '/docs/public-api'): string {
  return renderToStaticMarkup(<MemoryRouter initialEntries={[path]}>{content}</MemoryRouter>);
}

function layout(items = navItems): string {
  return render(
    <DocsLayout title="Example documentation" description="Example description" navItems={items}>
      <section id="overview">Overview content</section>
      <section id="setup">Setup content</section>
      <section id="examples">Example content</section>
    </DocsLayout>,
  );
}

// SSR has no DOM: inspect semantic elements, never CSS module hashes.
function elements(html: string, tag: string): string[] {
  return html.match(new RegExp(`<${tag}\\b[^>]*>[\\s\\S]*?</${tag}>`, 'g')) ?? [];
}

function openingTag(element: string): string {
  return element.slice(0, element.indexOf('>') + 1);
}

function sectionIndexes(html: string): string[] {
  return elements(html, 'nav').filter((nav) => openingTag(nav).includes('aria-label="On this page"'));
}

function anchors(html: string): string[] {
  return elements(html, 'a');
}

function href(anchor: string): string | undefined {
  return openingTag(anchor).match(/\bhref="([^"]*)"/)?.[1];
}

function text(element: string): string {
  return element.replace(/<[^>]*>/g, '').trim();
}

function sectionDetails(html: string): string[] {
  return elements(html, 'details').filter((details) =>
    elements(details, 'summary').some((summary) => text(summary) === 'On this page'),
  );
}

describe('DocsLayout section navigation', () => {
  it('renders every supplied native anchor with its href and label in both labeled indexes', () => {
    const html = layout();
    const indexes = sectionIndexes(html);
    expect(indexes).toHaveLength(2);
    for (const index of indexes) {
      expect(anchors(index).map((anchor) => ({ href: href(anchor), label: text(anchor) }))).toEqual([
        { href: '#overview', label: 'Overview' },
        { href: '#setup', label: 'Setup &amp; configuration' },
        { href: '#examples', label: 'Examples' },
      ]);
      expect(index).not.toContain('<button');
    }
    for (const item of navItems) {
      expect(anchors(html).filter((anchor) => href(anchor) === item.href)).toHaveLength(2);
    }
    expect(html).toContain('<h1');
    expect(html).toContain('Example documentation');
    expect(html).toContain('Example description');
  });

  it('keeps documentation on the left and puts the desktop index in a separate right aside', () => {
    const html = layout();
    const asides = elements(html, 'aside');
    expect(asides).toHaveLength(2);
    for (const link of docsLinks) {
      expect(anchors(asides[0]).some((anchor) => href(anchor) === link.href && text(anchor) === link.label)).toBe(true);
    }
    expect(sectionIndexes(asides[0])).toHaveLength(0);
    expect(sectionIndexes(asides[1])).toHaveLength(1);
    expect(anchors(asides[1]).every((anchor) => href(anchor)?.startsWith('#'))).toBe(true);
    expect(html.indexOf(asides[0])).toBeLessThan(html.indexOf('<main'));
    expect(html.indexOf(asides[1])).toBeGreaterThan(html.indexOf('</main>'));
  });

  it('provides a second, initially collapsed mobile disclosure above the page content', () => {
    const html = layout();
    const details = elements(html, 'details');
    expect(details).toHaveLength(1);
    const indexes = sectionDetails(html);
    expect(indexes).toHaveLength(1);
    expect(details[0]).toBe(indexes[0]);
    expect(openingTag(indexes[0])).not.toMatch(/\sopen(?:[\s=>])/);
    expect(elements(indexes[0], 'summary')).toHaveLength(1);
    expect(sectionIndexes(indexes[0])).toHaveLength(1);
    expect(html.indexOf(indexes[0])).toBeLessThan(html.indexOf('<section id="overview"'));

  });

  it('initially announces only the first section as the current location in both variants', () => {
    const indexes = sectionIndexes(layout());
    expect(indexes).toHaveLength(2);
    for (const index of indexes) {
      const links = anchors(index);
      expect(links).toHaveLength(navItems.length);
      expect(openingTag(links[0])).toContain('aria-current="location"');
      for (const link of links.slice(1)) expect(openingTag(link)).not.toContain('aria-current=');
      expect(index).not.toContain('aria-current="page"');
    }
  });

  it.each(docsLinks)('announces $href as the current documentation page, not section', ({ href: path }) => {
    const html = render(
      <DocsLayout title="Docs" description="Description" navItems={navItems}>Content</DocsLayout>,
      path,
    );
    const pageLinks = anchors(html).filter((anchor) => docsLinks.some((link) => link.href === href(anchor)));
    expect(pageLinks).toHaveLength(docsLinks.length);
    for (const link of pageLinks) {
      if (href(link) === path) expect(openingTag(link)).toContain('aria-current="page"');
      else expect(openingTag(link)).not.toContain('aria-current=');
    }
  });

  it('omits both section indexes and their disclosure when navItems is empty', () => {
    const html = layout([]);
    expect(sectionIndexes(html)).toHaveLength(0);
    expect(sectionDetails(html)).toHaveLength(0);
    expect(html).not.toContain('On this page');
    expect(html).not.toContain('aria-current="location"');
    expect(html).toContain('Overview content');
    for (const link of docsLinks) expect(html).toContain(`href="${link.href}"`);
  });
});

const pages = [
  { path: '/docs/quick-start', Component: QuickStart },
  { path: '/docs/public-api', Component: PublicApi },
  { path: '/docs/agent-to-agent', Component: AgentToAgent },
  { path: '/docs/automations', Component: Automations },
  { path: '/docs/faq', Component: FAQ },
];

describe('real documentation page indexes', () => {
  it.each(pages)('$path resolves every desktop and mobile index href to a real content id', ({ path, Component }) => {
    const html = render(<Component />, path);
    const indexes = sectionIndexes(html);
    expect(indexes).toHaveLength(2);
    const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
    const main = elements(html, 'main')[0];
    expect(main).toBeDefined();
    const contentIds = [...main.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
    for (const index of indexes) {
      const links = anchors(index);
      expect(links.length).toBeGreaterThan(0);
      for (const link of links) {
        const target = href(link);
        expect(target).toMatch(/^#[^#\s]+$/);
        const id = target!.slice(1);
        expect(contentIds).toContain(id);
        expect(ids.filter((candidate) => candidate === id)).toHaveLength(1);
        expect(text(link).length).toBeGreaterThan(0);
      }
    }
    expect(anchors(indexes[0]).map(href)).toEqual(anchors(indexes[1]).map(href));
  });

  it('includes all six embedded-widget sublinks in both Quick Start indexes', () => {
    const html = render(<QuickStart />, '/docs/quick-start');
    const indexes = sectionIndexes(html);
    expect(indexes).toHaveLength(2);
    for (const id of ['widget-floating', 'widget-options', 'widget-inline', 'widget-guests', 'widget-sections', 'widget-controls']) {
      expect(html).toContain(`id="${id}"`);
      for (const index of indexes) {
        expect(anchors(index).filter((anchor) => href(anchor) === `#${id}`)).toHaveLength(1);
      }
    }
  });
});
