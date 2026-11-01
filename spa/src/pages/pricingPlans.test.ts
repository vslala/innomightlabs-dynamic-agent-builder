import { describe, expect, it } from 'vitest';
import type { PricingTier } from '../types/pricing';
import { formatLimit, includesLine, isCustom, isFree } from './pricingPlans';

const tier = (name: string, monthly: string): PricingTier => ({
  name,
  badge: '',
  description: '',
  prices: { monthly, annual: monthly },
  ctaLabel: '',
  ctaHref: '',
  features: [],
  limits: { agents: 1, messages_per_month: 1, kb_pages: 1, memory_blocks: 1, lead_forms: 1, lead_captures_per_month: 1 },
});

describe('pricing plans', () => {
  it('reads 0 as unlimited and groups thousands', () => {
    expect(formatLimit(0)).toBe('Unlimited');
    expect(formatLimit(10000)).toBe('10,000');
  });

  it('builds each card on the one before it', () => {
    const plans = [tier('Free', '£0'), tier('Business', '£49')];
    expect(includesLine(plans, 0)).toBeNull();
    expect(includesLine(plans, 1)).toBe('Everything in Free, plus:');
  });

  it('knows a free plan by its zero price', () => {
    expect(isFree(tier('Free', '£0'))).toBe(true);
    expect(isFree(tier('Business', '£49'))).toBe(false);
    expect(isFree(tier('Enterprise', 'Custom'))).toBe(false);
  });

  it('treats custom pricing as a conversation', () => {
    expect(isCustom(tier('Enterprise', 'Custom'))).toBe(true);
    expect(isCustom(tier('Growth', '£149'))).toBe(false);
  });
});
