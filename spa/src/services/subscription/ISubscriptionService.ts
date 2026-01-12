import type { Subscriber, SubscribeResult } from '../../types/subscription';

export interface ISubscriptionService {
  subscribe(email: string): Promise<SubscribeResult>;
  getSubscribers(): Promise<Subscriber[]>;
  isSubscribed(email: string): Promise<boolean>;
}
