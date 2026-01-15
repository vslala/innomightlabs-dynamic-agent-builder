/**
 * Protected Route component that ensures user is authenticated.
 *
 * Features:
 * 1. Checks for valid auth token on mount
 * 2. Validates token with backend on mount
 * 3. Redirects to home/login if not authenticated
 * 4. Shows loading state while validating
 */

import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { authService } from "../../services/auth";

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const [isValidating, setIsValidating] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const validateAuth = async () => {
      // Quick check - do we have a token at all?
      if (!authService.getToken()) {
        setIsAuthenticated(false);
        setIsValidating(false);
        return;
      }

      // Check if token is expired locally
      if (!authService.isAuthenticated()) {
        // Token is expired, but the backend middleware might refresh it
        // Try to call the backend to trigger refresh
        try {
          await authService.getCurrentUser();
          // If we get here, either token was valid or got refreshed
          setIsAuthenticated(true);
        } catch {
          // Token is invalid and couldn't be refreshed
          authService.removeToken();
          setIsAuthenticated(false);
        }
      } else {
        // Token looks valid locally, but let's validate with backend
        try {
          await authService.getCurrentUser();
          setIsAuthenticated(true);
        } catch {
          // Token is invalid on backend
          authService.removeToken();
          setIsAuthenticated(false);
        }
      }

      setIsValidating(false);
    };

    validateAuth();
  }, []);

  if (isValidating) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--bg-dark)]">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-[var(--gradient-start)] border-t-transparent" />
          <p className="text-sm text-[var(--text-muted)]">Validating session...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    // Redirect to home page, preserving the intended destination
    return <Navigate to="/" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
