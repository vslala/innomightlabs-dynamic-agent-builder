import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import styles from './LoginSuccess.module.css';

interface UserInfo {
  email: string;
  name: string;
  picture: string;
}

export function LoginSuccess() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

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
      setUserInfo({
        email: payload.sub,
        name: payload.name,
        picture: payload.picture,
      });
    } catch {
      console.error('Failed to decode token');
    }

    setLoading(false);
  }, [searchParams, navigate]);

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
          <h1>Welcome to Beta!</h1>
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
            Thank you for joining our beta program! We're still building out the
            platform and will notify you when new features are available.
          </p>
        </div>

        <button onClick={() => navigate('/')} className={styles.button}>
          Back to Home
        </button>
      </div>
    </div>
  );
}
