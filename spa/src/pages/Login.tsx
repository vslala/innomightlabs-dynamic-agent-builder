import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authService } from '../services/auth';
import { httpClient } from '../services/http';
import { Navbar } from '../components/Navbar';
import { Footer } from '../components/Footer';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import styles from './Login.module.css';

const isLocalhost = window.location.hostname === 'localhost';

export function Login() {
  const navigate = useNavigate();
  const isAuthenticated = authService.isAuthenticated();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard');
    }
  }, [isAuthenticated, navigate]);

  const handleGoogleLogin = () => {
    window.location.href = `${import.meta.env.VITE_API_BASE_URL}/auth/google`;
  };

  const handleEmailLogin = () => {
    window.location.href = `${import.meta.env.VITE_API_BASE_URL}/auth/cognito`;
  };

  const handleLocalAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      // Try signup first
      const response = await httpClient.post<{ token: string; email: string; name: string }>(
        '/auth/local/signup',
        { username, password },
        { skipAuth: true }
      );

      localStorage.setItem('auth_token', response.token);
      navigate('/dashboard');
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const httpError = err as { response?: { data?: { detail?: string }; status?: number } };

        // If username already taken, try login instead
        if (httpError.response?.data?.detail === 'Username already taken') {
          try {
            const loginResponse = await httpClient.post<{ token: string; email: string; name: string }>(
              '/auth/local/login',
              { username, password },
              { skipAuth: true }
            );

            localStorage.setItem('auth_token', loginResponse.token);
            navigate('/dashboard');
            return;
          } catch (loginErr: unknown) {
            if (loginErr && typeof loginErr === 'object' && 'response' in loginErr) {
              const loginHttpError = loginErr as { response?: { data?: { detail?: string } } };
              setError(loginHttpError.response?.data?.detail || 'Invalid username or password.');
            } else {
              setError('Invalid username or password.');
            }
          }
        } else {
          setError(httpError.response?.data?.detail || 'Failed to authenticate. Please try again.');
        }
      } else {
        setError('Failed to authenticate. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Navbar />
      <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.header}>
          <h1>Welcome Back</h1>
          <p className={styles.subtitle}>Sign in to access your dashboard</p>
        </div>

        <div className={styles.buttonGroup}>
          <button
            onClick={handleGoogleLogin}
            className={styles.googleButton}
            type="button"
          >
            <svg className={styles.icon} viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                fill="#4285F4"
              />
              <path
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                fill="#34A853"
              />
              <path
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                fill="#FBBC05"
              />
              <path
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                fill="#EA4335"
              />
            </svg>
            Continue with Google
          </button>

          <div className={styles.divider}>
            <span>or</span>
          </div>

          <button
            onClick={handleEmailLogin}
            className={styles.emailButton}
            type="button"
          >
            <svg className={styles.icon} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M3 8L10.89 13.26C11.2187 13.4793 11.6049 13.5963 12 13.5963C12.3951 13.5963 12.7813 13.4793 13.11 13.26L21 8M5 19H19C19.5304 19 20.0391 18.7893 20.4142 18.4142C20.7893 18.0391 21 17.5304 21 17V7C21 6.46957 20.7893 5.96086 20.4142 5.58579C20.0391 5.21071 19.5304 5 19 5H5C4.46957 5 3.96086 5.21071 3.58579 5.58579C3.21071 5.96086 3 6.46957 3 7V17C3 17.5304 3.21071 18.0391 3.58579 18.4142C3.96086 18.7893 4.46957 19 5 19Z"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Continue with Email
          </button>

          {isLocalhost && (
            <>
              <div className={styles.divider}>
                <span>or</span>
              </div>

              <form onSubmit={handleLocalAuth} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {error && (
                  <div
                    style={{
                      padding: '0.75rem',
                      borderRadius: '0.5rem',
                      backgroundColor: 'rgba(248, 113, 113, 0.1)',
                      border: '1px solid rgba(248, 113, 113, 0.2)',
                      color: '#f87171',
                      fontSize: '0.875rem',
                    }}
                  >
                    {error}
                  </div>
                )}
                <Input
                  type="text"
                  placeholder="Username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  disabled={loading}
                />
                <Input
                  type="password"
                  placeholder="Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={loading}
                />
                <Button type="submit" disabled={loading}>
                  {loading ? 'Authenticating...' : 'Login / Sign Up (Dev Only)'}
                </Button>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center' }}>
                  Local development only - auto-creates {username || 'username'}@example.com
                </p>
              </form>
            </>
          )}
        </div>

        <p className={styles.terms}>
          By continuing, you agree to our{' '}
          <a href="/legal/terms" className={styles.link}>
            Terms of Service
          </a>{' '}
          and{' '}
          <a href="/legal/pricing" className={styles.link}>
            Privacy Policy
          </a>
        </p>
      </div>
    </div>
      <Footer />
    </>
  );
}
