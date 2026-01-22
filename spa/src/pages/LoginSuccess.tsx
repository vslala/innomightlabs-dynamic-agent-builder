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

      // Redirect to dashboard after short delay
      setTimeout(() => {
        navigate('/dashboard');
      }, 1500);
    } catch {
      console.error('Failed to decode token');
      navigate('/');
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
            Redirecting you to your dashboard...
          </p>
        </div>

        <button onClick={() => navigate('/dashboard')} className={styles.button}>
          Go to Dashboard
        </button>
      </div>
    </div>
  );
}
