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
}

export interface PricingFaq {
  question: string;
  answer: string;
}

export interface PricingResponse {
  tiers: PricingTier[];
  faqs: PricingFaq[];
}
