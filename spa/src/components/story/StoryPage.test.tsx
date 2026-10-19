import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { LandingPage } from '../../pages/LandingPage';
import { IlaPage } from '../../pages/features/IlaPage';
import { AgentsPage } from '../../pages/features/AgentsPage';
import { LeadsPage } from '../../pages/features/LeadsPage';
import { AutomationsPage } from '../../pages/features/AutomationsPage';
import { FEATURES } from '../../routes/features';
import { PUBLIC_PAGES, buildSitemap, indexablePaths } from '../../routes/publicPages';
import { storyClasses } from './storyClasses';
import shared from './StoryPage.module.css';

vi.mock('../../services/auth', () => ({ authService: { isAuthenticated: () => false } }));

const pages = [
  { path: '/', Component: LandingPage },
  { path: '/features/ila', Component: IlaPage },
  { path: '/features/agents', Component: AgentsPage },
  { path: '/features/leads', Component: LeadsPage },
  { path: '/features/automations', Component: AutomationsPage },
];

describe('public story integration', () => {
  for (const { path, Component } of pages) {
    it(`${path} shares one header and footer and links to the other stories`, () => {
      const html = renderToStaticMarkup(<MemoryRouter initialEntries={[path]}><Component /></MemoryRouter>);
      expect(html.match(/aria-label="Main navigation"/g)).toHaveLength(1);
      expect(html.match(/aria-label="Footer navigation"/g)).toHaveLength(1);
      expect(html.match(/<main\b/g)).toHaveLength(1);
      expect(html).toContain('aria-controls="feature-navigation"');
      expect(html).toContain('aria-controls="public-navigation"');
      for (const feature of FEATURES) expect(html).toContain(`href="${feature.path}"`);
      expect(html).toContain('href="/login"');
      expect(html).not.toMatch(/href="(?:feature-[^"]+\.html|#)"/);
      expect(html).not.toContain('<script');
    });
  }
  it('registers every dropdown destination for routing and generated public HTML/sitemap', () => {
    const sitemap = buildSitemap(indexablePaths());
    for (const feature of FEATURES) {
      expect(PUBLIC_PAGES).toContainEqual({ path: feature.path, indexed: true, title: feature.title, section: 'Product' });
      expect(sitemap).toContain(`https://innomightlabs.com${feature.path}`);
    }
  });
  it('retains shared and local refinements and ignores disabled classes', () => {
    const cx = storyClasses({ win: 'local-window', localOnly: 'local-only' });
    const tokens = cx('win localOnly', false, undefined).split(' ');
    expect(tokens).toContain(shared.win);
    expect(tokens).toContain('local-window');
    expect(tokens).toContain('local-only');
    expect(tokens).not.toContain('undefined');
    expect(tokens).not.toContain('false');
  });
});
