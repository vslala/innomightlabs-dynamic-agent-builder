import { ApiPricingService } from './ApiPricingService';
import type { IPricingService } from './IPricingService';

export type { IPricingService };

export const pricingService: IPricingService = new ApiPricingService();
