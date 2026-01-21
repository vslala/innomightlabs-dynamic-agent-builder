import type { PricingResponse } from '../../types/pricing';

export interface IPricingService {
  getPricing(): Promise<PricingResponse>;
  createCheckoutSession(
    planKey: string,
    billingCycle: string,
    userEmail?: string
  ): Promise<{ url: string }>;
}
