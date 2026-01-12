export interface Subscriber {
  id: string;
  email: string;
  subscribedAt: string;
}

export interface SubscribeResult {
  success: boolean;
  message: string;
}
