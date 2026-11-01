/**
 * PKCE (RFC 7636) for the app's sign-in: the verifier never leaves the device, so a login code intercepted on
 * its way back through the URL scheme is useless to whoever caught it.
 */

/** 32 random bytes as base64url: a 43-character verifier, as the API expects. */
export function createVerifier(): string {
  return base64Url(crypto.getRandomValues(new Uint8Array(32)));
}

/** The S256 challenge for a verifier: base64url(SHA-256(verifier)), without padding. */
export async function challengeFor(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64Url(new Uint8Array(digest));
}

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
