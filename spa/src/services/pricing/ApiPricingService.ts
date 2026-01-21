import { httpClient } from '../http';
import type { PricingResponse } from '../../types/pricing';
import type { IPricingService } from './IPricingService';

export class ApiPricingService implements IPricingService {
  async getPricing(): Promise<PricingResponse> {
    return httpClient.get<PricingResponse>('/payments/stripe/pricing', { skipAuth: true });
  }

  async createCheckoutSession(
    planKey: string,
    billingCycle: string,
    customerEmail?: string
  ): Promise<{ url: string }> {
    return httpClient.post<{ url: string }>(
      '/payments/stripe/checkout-session',
      { planKey, billingCycle, customerEmail, clientReferenceId: customerEmail },
      { skipAuth: true }
    );
  }
}
