/** @jsxImportSource preact */
import { GoogleIcon } from './Icons';

interface LoginScreenProps {
  agentName: string;
  onLogin: () => void;
  isLoading: boolean;
}

export function LoginScreen({ agentName, onLogin, isLoading }: LoginScreenProps) {
  return (
    <div className="innomight-login">
      <div className="innomight-login-title">Welcome to {agentName}</div>
      <div className="innomight-login-subtitle">
        Sign in to start chatting
      </div>
      <button
        className="innomight-google-btn"
        onClick={onLogin}
        disabled={isLoading}
      >
        {isLoading ? (
          <div className="innomight-spinner" />
        ) : (
          <>
            <GoogleIcon />
            <span>Continue with Google</span>
          </>
        )}
      </button>
    </div>
  );
}
