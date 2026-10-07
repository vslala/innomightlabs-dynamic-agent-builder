/// <reference types="node" />
// Node types only here: this test reads styles.css from disk, since Vitest stubs CSS imports.
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { readBootstrap } from "./bootstrap";
import { LoginPanel } from "./components/LoginPanel";
import { rememberGuestEmail } from "./session";

const props = {
  publicKey: "entry-key", allowGuests: false, agentName: "Mira", description: null,
  greeting: "Hello!", answersOnSignIn: true, isSigningIn: false, error: null,
  onSignIn: vi.fn(), onGuestSession: vi.fn(),
};

describe("guest entry markup", () => {
  it("leaves Google-only keys unchanged", () => {
    const html = renderToStaticMarkup(<LoginPanel {...props} />);
    expect(html).toContain("Continue with Google");
    expect(html).not.toContain("Continue as guest");
    expect(html).not.toContain('type="email"');
  });
  it("offers both methods, uses the server timeout, and prefills the remembered email", () => {
    rememberGuestEmail(props.publicKey, "returning@example.com");
    const html = renderToStaticMarkup(<LoginPanel {...props} allowGuests timeoutMinutes={27} />);
    expect(html).toContain("Continue as guest");
    expect(html).toContain("Continue with Google");
    expect(html).toContain("27 minutes without messages");
    expect(html).toContain('value="returning@example.com"');
    expect(html).toContain('for="guest-email"');
    expect(html).toContain('aria-describedby="guest-notice guest-status"');
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain('aria-busy="false"');
    expect(html).not.toContain("ie-spinner");
    expect(html).toContain("Email delivery is not guaranteed");
    expect(html).toContain("https://innomightlabs.com/legal/privacy");
  });
  it("does not invent a timeout when bootstrap has none", () => {
    const html = renderToStaticMarkup(<LoginPanel {...props} allowGuests />);
    expect(html).toContain("a period without messages");
    expect(html).not.toContain("60 minutes");
  });
  it("disables guest submission during Google sign-in", () => {
    const html = renderToStaticMarkup(<LoginPanel {...props} allowGuests isSigningIn />);
    expect(html).toMatch(/<input[^>]*disabled=""/);
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*disabled=""/);
  });
  it("turns guest motion off for reduced-motion users, including shimmer pseudo-elements", () => {
    const css = readFileSync(new URL("./styles.css", import.meta.url), "utf8");
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*\*::before[\s\S]*animation: none !important/);
  });
});

describe("trusted bootstrap guest opt-in", () => {
  function bootstrap(body: object) {
    return readBootstrap({ getElementById: () => ({ textContent: JSON.stringify(body) }) } as unknown as Document);
  }
  it("defaults legacy shells to guests off", () => {
    expect(bootstrap({ public_key: "pk" }).allow_guests).toBe(false);
  });
  it("requires an explicit boolean and preserves the effective timeout", () => {
    expect(bootstrap({ allow_guests: "true" }).allow_guests).toBe(false);
    expect(bootstrap({ allow_guests: true, guest_session_timeout_minutes: 37 })).toMatchObject({
      allow_guests: true, guest_session_timeout_minutes: 37,
    });
  });
});
