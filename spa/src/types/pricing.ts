/** A tier's capacity, as enforced by the API. 0 means unlimited. */
export interface PricingLimits {
  agents: number;
  messages_per_month: number;
  kb_pages: number;
  memory_blocks: number;
  lead_forms: number;
  lead_captures_per_month: number;
}

export interface PricingTier {
  name: string;
  badge: string;
  description: string;
  prices: {
    monthly: string;
    annual: string;
  };
  planKey?: string | null;
  ctaLabel: string;
  ctaHref: string;
  highlighted?: boolean;
  features: string[];
  limits: PricingLimits;
}

/** A one-off service sold beside the plans, such as the done-with-you setup. */
export interface PricingAddon {
  name: string;
  price: string;
  period: string;
  description: string;
  features: string[];
  ctaLabel: string;
  ctaHref: string;
}

export interface PricingFaq {
  question: string;
  answer: string;
}

export interface PricingResponse {
  tiers: PricingTier[];
  addons: PricingAddon[];
  faqs: PricingFaq[];
}
