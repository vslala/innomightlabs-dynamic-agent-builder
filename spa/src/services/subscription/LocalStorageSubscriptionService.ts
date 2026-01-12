import type { Subscriber, SubscribeResult } from '../../types/subscription';
import { encrypt, decrypt } from '../../utils/crypto';
import type { ISubscriptionService } from './ISubscriptionService';

const STORAGE_KEY = 'waitlist_subscribers';

export class LocalStorageSubscriptionService implements ISubscriptionService {
  async subscribe(email: string): Promise<SubscribeResult> {
    const normalizedEmail = email.toLowerCase().trim();

    if (await this.isSubscribed(normalizedEmail)) {
      return {
        success: false,
        message: 'This email is already on the waitlist.',
      };
    }

    const subscribers = await this.getSubscribers();
    const newSubscriber: Subscriber = {
      id: crypto.randomUUID(),
      email: normalizedEmail,
      subscribedAt: new Date().toISOString(),
    };

    subscribers.push(newSubscriber);
    await this.saveSubscribers(subscribers);

    return {
      success: true,
      message: 'Successfully joined the waitlist!',
    };
  }

  async getSubscribers(): Promise<Subscriber[]> {
    const encryptedData = localStorage.getItem(STORAGE_KEY);
    if (!encryptedData) {
      return [];
    }

    try {
      const decryptedData = await decrypt(encryptedData);
      return JSON.parse(decryptedData);
    } catch {
      return [];
    }
  }

  async isSubscribed(email: string): Promise<boolean> {
    const subscribers = await this.getSubscribers();
    const normalizedEmail = email.toLowerCase().trim();
    return subscribers.some((s) => s.email === normalizedEmail);
  }

  private async saveSubscribers(subscribers: Subscriber[]): Promise<void> {
    const encryptedData = await encrypt(JSON.stringify(subscribers));
    localStorage.setItem(STORAGE_KEY, encryptedData);
  }
}
