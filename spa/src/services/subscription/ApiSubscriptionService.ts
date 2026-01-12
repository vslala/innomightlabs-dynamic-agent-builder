import type { Subscriber, SubscribeResult } from '../../types/subscription';
import type { ISubscriptionService } from './ISubscriptionService';

export class ApiSubscriptionService implements ISubscriptionService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = import.meta.env.VITE_API_BASE_URL || '';
  }

  async subscribe(email: string): Promise<SubscribeResult> {
    const response = await fetch(`${this.baseUrl}/api/waitlist/subscribe`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email: email.toLowerCase().trim() }),
    });

    const data = await response.json();

    if (!response.ok) {
      return {
        success: false,
        message: data.message || 'Failed to subscribe. Please try again.',
      };
    }

    return {
      success: true,
      message: data.message || 'Successfully joined the waitlist!',
    };
  }

  async getSubscribers(): Promise<Subscriber[]> {
    const response = await fetch(`${this.baseUrl}/api/waitlist/subscribers`);

    if (!response.ok) {
      throw new Error('Failed to fetch subscribers');
    }

    return response.json();
  }

  async isSubscribed(email: string): Promise<boolean> {
    const response = await fetch(
      `${this.baseUrl}/api/waitlist/check?email=${encodeURIComponent(email.toLowerCase().trim())}`
    );

    if (!response.ok) {
      return false;
    }

    const data = await response.json();
    return data.isSubscribed;
  }
}
