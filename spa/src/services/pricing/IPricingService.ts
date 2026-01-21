import type { PricingResponse } from '../../types/pricing';

export interface IPricingService {
  getPricing(): Promise<PricingResponse>;
  createCheckoutSession(
    planKey: string,
    billingCycle: string,
    customerEmail?: string
  ): Promise<{ url: string }>;
}
