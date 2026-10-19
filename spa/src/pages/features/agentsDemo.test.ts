import { describe, expect, it } from 'vitest';
import { AGENTS, LAYERS, SITE, buildAnswer, findAgents, type Layer } from './agentsDemo';

const favorites = new Set(AGENTS.filter(agent => agent.favorite).map(agent => agent.id));

describe('Agents story anatomy', () => {
  it('is honest without knowledge and cites menu facts only with knowledge', () => {
    expect(buildAnswer(new Set())).toContain('I am not sure what is on the menu');
    expect(buildAnswer(new Set(['knowledge']))).toBe('Yes, our gluten-free brownies and almond cake are $4.50 each.');
  });

  it('composes every combination of independently switchable layers', () => {
    for (let mask = 0; mask < 16; mask++) {
      const selected = new Set<Layer>(LAYERS.filter((_, index) => mask & (1 << index)).map(([key]) => key));
      const answer = buildAnswer(selected);
      expect(answer.includes('$4.50')).toBe(selected.has('knowledge'));
      expect(answer.includes('I can set some aside')).toBe(selected.has('skills'));
      expect(answer.includes('Saturday 10am pickup is free')).toBe(selected.has('connector'));
      expect(answer.includes('Welcome back, Sarah!')).toBe(selected.has('memory'));
      expect(answer.includes("daughter's birthday order")).toBe(selected.has('memory'));
    }
  });

  it('keeps the complete approved illustrative crawl', () => {
    expect(SITE).toHaveLength(14);
    expect(SITE).toContain('/allergens');
    expect(Math.round(SITE.length / SITE.length * 38) * 11).toBe(418);
  });
});

describe('Agents story finder', () => {
  it('starts with 240 agents with favorites first, without mutating the catalog', () => {
    const hits = findAgents('', new Set(), favorites);
    expect(hits).toHaveLength(240);
    expect(hits.slice(0, favorites.size).every(agent => favorites.has(agent.id))).toBe(true);
    expect(AGENTS[1].id).toBe(1);
  });

  it('matches case-insensitive multiple words and ANDs capability filters', () => {
    const hits = findAgents('  INV chas  ', new Set(['kb', 'conn', 'skill']), favorites);
    expect(hits.length).toBeGreaterThan(0);
    expect(hits.every(agent => agent.name.toLowerCase().includes('inv') && agent.name.toLowerCase().includes('chas') && agent.kb && agent.conn && agent.skill)).toBe(true);
    expect(findAgents('', new Set(['kb']), favorites)).toHaveLength(80);
    expect(findAgents('', new Set(['conn']), favorites)).toHaveLength(60);
    expect(findAgents('', new Set(['skill']), favorites)).toHaveLength(120);
  });

  it('treats punctuation and markup as text and returns an empty state', () => {
    for (const query of ['[', '.*', '<script>', 'no such agent']) {
      expect(findAgents(query, new Set(), favorites)).toEqual([]);
    }
  });

  it('reflects starring and unstarring without changing shared example data', () => {
    const selected = new Set([239]);
    expect(findAgents('', new Set(), selected)[0].id).toBe(239);
    selected.clear();
    expect(findAgents('', new Set(), selected)[0].id).toBe(0);
    expect(AGENTS[239].favorite).toBe(false);
  });
});
