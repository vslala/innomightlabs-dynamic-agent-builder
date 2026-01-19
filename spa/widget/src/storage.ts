/**
 * Storage utilities for persisting visitor session data.
 */

import { Visitor, Conversation, STORAGE_KEYS } from './types';

/**
 * Get the visitor token from localStorage.
 */
export function getVisitorToken(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEYS.VISITOR_TOKEN);
  } catch {
    return null;
  }
}

/**
 * Set the visitor token in localStorage.
 */
export function setVisitorToken(token: string): void {
  try {
    localStorage.setItem(STORAGE_KEYS.VISITOR_TOKEN, token);
  } catch {
    // localStorage not available
  }
}

/**
 * Clear the visitor token from localStorage.
 */
export function clearVisitorToken(): void {
  try {
    localStorage.removeItem(STORAGE_KEYS.VISITOR_TOKEN);
  } catch {
    // localStorage not available
  }
}

/**
 * Get visitor info from localStorage.
 */
export function getVisitorInfo(): Visitor | null {
  try {
    const data = localStorage.getItem(STORAGE_KEYS.VISITOR_INFO);
    return data ? JSON.parse(data) : null;
  } catch {
    return null;
  }
}

/**
 * Set visitor info in localStorage.
 */
export function setVisitorInfo(visitor: Visitor): void {
  try {
    localStorage.setItem(STORAGE_KEYS.VISITOR_INFO, JSON.stringify(visitor));
  } catch {
    // localStorage not available
  }
}

/**
 * Clear visitor info from localStorage.
 */
export function clearVisitorInfo(): void {
  try {
    localStorage.removeItem(STORAGE_KEYS.VISITOR_INFO);
  } catch {
    // localStorage not available
  }
}

/**
 * Get current conversation from localStorage.
 */
export function getCurrentConversation(): Conversation | null {
  try {
    const data = localStorage.getItem(STORAGE_KEYS.CURRENT_CONVERSATION);
    return data ? JSON.parse(data) : null;
  } catch {
    return null;
  }
}

/**
 * Set current conversation in localStorage.
 */
export function setCurrentConversation(conversation: Conversation): void {
  try {
    localStorage.setItem(STORAGE_KEYS.CURRENT_CONVERSATION, JSON.stringify(conversation));
  } catch {
    // localStorage not available
  }
}

/**
 * Clear all widget data from localStorage.
 */
export function clearAllData(): void {
  clearVisitorToken();
  clearVisitorInfo();
  try {
    localStorage.removeItem(STORAGE_KEYS.CURRENT_CONVERSATION);
  } catch {
    // localStorage not available
  }
}

/**
 * Check if visitor session is valid (token exists and not expired).
 */
export function isSessionValid(): boolean {
  const token = getVisitorToken();
  if (!token) return false;

  try {
    // Decode JWT payload (without verification - server will verify)
    const payload = JSON.parse(atob(token.split('.')[1]));
    const exp = payload.exp * 1000; // Convert to milliseconds
    return Date.now() < exp;
  } catch {
    return false;
  }
}
