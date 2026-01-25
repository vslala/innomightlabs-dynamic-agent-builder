import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { pricingService } from '../services/pricing';
import styles from './LoginSuccess.module.css';

interface UserInfo {
  email: string;
  name: string;
  picture: string;
}

interface PendingCheckout {
  planKey: string;
  billingCycle: string;
  timestamp: number;
}

export function LoginSuccess() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [redirectMessage, setRedirectMessage] = useState('Redirecting you to your dashboard...');

  useEffect(() => {
    const token = searchParams.get('token');

    if (!token) {
      navigate('/');
      return;
    }

    // Store token in localStorage
    localStorage.setItem('auth_token', token);

    // Decode JWT to get user info (basic decode, not verification)
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      const userInfo = {
        email: payload.sub,
        name: payload.name,
        picture: payload.picture,
      };
      setUserInfo(userInfo);

      // Check for pending checkout
      const pendingCheckoutStr = sessionStorage.getItem('pendingCheckout');
      if (pendingCheckoutStr) {
        const pendingCheckout: PendingCheckout = JSON.parse(pendingCheckoutStr);

        // Check if checkout is still valid (within 10 minutes)
        const tenMinutes = 10 * 60 * 1000;
        if (Date.now() - pendingCheckout.timestamp < tenMinutes) {
          // Update message to reflect checkout flow
          setRedirectMessage('Completing your checkout...');

          // Clear the pending checkout
          sessionStorage.removeItem('pendingCheckout');

          // Complete the checkout flow
          completeCheckout(pendingCheckout.planKey, pendingCheckout.billingCycle, userInfo.email);
          return;
        } else {
          // Checkout expired, clear it
          sessionStorage.removeItem('pendingCheckout');
        }
      }

      // No pending checkout, redirect to dashboard after short delay
      setTimeout(() => {
        navigate('/dashboard');
      }, 1500);
    } catch {
      console.error('Failed to decode token');
      navigate('/');
    }

    setLoading(false);
  }, [searchParams, navigate]);

  const completeCheckout = async (planKey: string, billingCycle: string, email: string) => {
    try {
      const response = await pricingService.createCheckoutSession(
        planKey,
        billingCycle,
        email
      );

      // Redirect to Stripe checkout
      window.location.href = response.url;
    } catch (error) {
      console.error('Failed to complete checkout:', error);
      // On error, redirect to pricing page with the plan pre-selected
      setTimeout(() => {
        navigate('/pricing');
      }, 1500);
    }
  };

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.card}>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.header}>
          <h1>Welcome to InnoMight Labs</h1>
          <p className={styles.subtitle}>You have successfully logged in</p>
        </div>

        {userInfo && (
          <div className={styles.userInfo}>
            {userInfo.picture && (
              <img
                src={userInfo.picture}
                alt={userInfo.name}
                className={styles.avatar}
              />
            )}
            <div className={styles.details}>
              <p className={styles.name}>{userInfo.name}</p>
              <p className={styles.email}>{userInfo.email}</p>
            </div>
          </div>
        )}

        <div className={styles.message}>
          <p>
            {redirectMessage}
          </p>
        </div>

        <button onClick={() => navigate('/dashboard')} className={styles.button}>
          Go to Dashboard
        </button>
      </div>
    </div>
  );
}
