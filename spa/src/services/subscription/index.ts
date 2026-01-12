import type { ISubscriptionService } from './ISubscriptionService';
import { LocalStorageSubscriptionService } from './LocalStorageSubscriptionService';
import { ApiSubscriptionService } from './ApiSubscriptionService';

export type { ISubscriptionService };

export const createSubscriptionService = (): ISubscriptionService => {
  const backend = import.meta.env.VITE_SUBSCRIPTION_BACKEND;

  if (backend === 'api') {
    return new ApiSubscriptionService();
  }

  return new LocalStorageSubscriptionService();
};

// Default instance
export const subscriptionService = createSubscriptionService();
