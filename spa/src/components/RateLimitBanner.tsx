import { useEffect, useState } from 'react';
import { Button } from './ui/button';
import styles from './RateLimitBanner.module.css';

interface RateLimitDetail {
  message: string;
  upgradeUrl?: string;
}

export function RateLimitBanner() {
  const [detail, setDetail] = useState<RateLimitDetail | null>(null);

  useEffect(() => {
    const handler = (event: Event) => {
      const customEvent = event as CustomEvent<RateLimitDetail>;
      if (customEvent.detail?.message) {
        setDetail(customEvent.detail);
      }
    };

    window.addEventListener('rate-limit', handler);
    return () => window.removeEventListener('rate-limit', handler);
  }, []);

  if (!detail) {
    return null;
  }

  return (
    <div className={styles.banner}>
      <div className={styles.content}>
        <span>{detail.message}</span>
        <a href={detail.upgradeUrl || '/pricing'} className={styles.link}>
          Upgrade plan
        </a>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className={styles.dismiss}
        onClick={() => setDetail(null)}
        aria-label="Dismiss notification"
      >
        ✕
      </Button>
    </div>
  );
}
