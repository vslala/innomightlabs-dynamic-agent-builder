/**
 * Authentication service for managing user auth state.
 */

import { httpClient } from "../http";

const AUTH_TOKEN_KEY = "auth_token";

export interface UserInfo {
  email: string;
  name: string;
  picture?: string;
}

export interface TokenPayload {
  sub: string;
  name: string;
  picture?: string;
  exp: number;
  iat: number;
}

class AuthService {
  /**
   * Get the current auth token from localStorage.
   */
  getToken(): string | null {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  }

  /**
   * Set the auth token in localStorage.
   */
  setToken(token: string): void {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  }

  /**
   * Remove the auth token from localStorage.
   */
  removeToken(): void {
    localStorage.removeItem(AUTH_TOKEN_KEY);
  }

  /**
   * Check if user is authenticated (has valid token).
   */
  isAuthenticated(): boolean {
    const token = this.getToken();
    if (!token) return false;

    try {
      const payload = this.decodeToken(token);
      // Check if token is expired
      const now = Math.floor(Date.now() / 1000);
      return payload.exp > now;
    } catch {
      return false;
    }
  }

  /**
   * Decode JWT token without verification (for reading payload only).
   */
  decodeToken(token: string): TokenPayload {
    const parts = token.split(".");
    if (parts.length !== 3) {
      throw new Error("Invalid token format");
    }

    const payload = JSON.parse(atob(parts[1]));
    return payload as TokenPayload;
  }

  /**
   * Get user info from current token.
   */
  getUserFromToken(): UserInfo | null {
    const token = this.getToken();
    if (!token) return null;

    try {
      const payload = this.decodeToken(token);
      return {
        email: payload.sub,
        name: payload.name,
        picture: payload.picture,
      };
    } catch {
      return null;
    }
  }

  /**
   * Fetch current user info from backend (validates token server-side).
   */
  async getCurrentUser(): Promise<UserInfo> {
    return httpClient.get<UserInfo>("/auth/me");
  }

  /**
   * Logout the user - clears token and redirects to home.
   */
  logout(): void {
    this.removeToken();
    window.location.href = "/";
  }

  /**
   * Get the Google OAuth login URL.
   */
  getGoogleLoginUrl(): string {
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
    return `${apiBaseUrl}/auth/google`;
  }
}

export const authService = new AuthService();
export default authService;
