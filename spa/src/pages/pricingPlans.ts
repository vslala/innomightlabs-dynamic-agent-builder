import type { PricingLimits, PricingTier } from '../types/pricing';

/** The comparison table's rows, in the order a business owner reads them. */
export const LIMIT_ROWS: ReadonlyArray<readonly [keyof PricingLimits, string]> = [
  ['agents', 'Agents'],
  ['messages_per_month', 'Messages a month'],
  ['kb_pages', 'Knowledge base pages'],
  ['lead_forms', 'Lead forms'],
  ['lead_captures_per_month', 'Leads a month'],
  ['memory_blocks', 'Memory blocks'],
];

export function formatLimit(value: number): string {
  return value === 0 ? 'Unlimited' : value.toLocaleString('en-US');
}

/** Custom-priced tiers (Enterprise) are a conversation, not a card with a price. */
export function isCustom(tier: PricingTier): boolean {
  return tier.prices.monthly === 'Custom';
}

/** A plan with a zero price, whatever the currency symbol. */
export function isFree(tier: PricingTier): boolean {
  return tier.prices.monthly.replace(/\D/g, '') === '0';
}

/** "Everything in Business, plus:" for every card after the first. */
export function includesLine(plans: PricingTier[], index: number): string | null {
  return index === 0 ? null : `Everything in ${plans[index - 1].name}, plus:`;
}
