/**
 * Authentication service for managing user auth state.
 */

import { platform } from "../../platform";
import { httpClient, setActiveAccountId } from "../http";

export interface UserInfo {
  userId: string;
  email: string;
  name: string;
  picture?: string;
}

export interface TokenPayload {
  /** The user_id. The email is a display-only claim. */
  sub: string;
  email: string;
  name: string;
  picture?: string;
  exp: number;
  iat: number;
}

class AuthService {
  /**
   * The current access token, from the platform (localStorage on the web, memory in the app).
   */
  getToken(): string | null {
    return platform().tokens.accessToken();
  }

  /**
   * Forget the session on this device: the token and the active-account choice.
   */
  removeToken(): void {
    void platform().tokens.clear();
    setActiveAccountId(null);
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
        userId: payload.sub,
        email: payload.email,
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
    const me = await httpClient.get<{ user_id: string; email: string; name: string; picture?: string }>("/auth/me");
    return { userId: me.user_id, email: me.email, name: me.name, picture: me.picture };
  }

  /**
   * Sign out: ends the session where the platform has one, forgets the account choice, goes home.
   */
  async logout(): Promise<void> {
    await platform().auth.end();
    setActiveAccountId(null);
    window.location.href = "/";
  }

  /**
   * Delete user account - marks user inactive and triggers cascade deletion.
   */
  async deleteAccount(): Promise<{ message: string; status: string }> {
    return httpClient.delete<{ message: string; status: string }>("/users/me");
  }
}

export const authService = new AuthService();
export default authService;
