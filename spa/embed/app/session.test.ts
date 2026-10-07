import { describe, expect, it } from "vitest";

import {
  clearSession,
  endLocalSession,
  loadGuestEmail,
  type Session,
  conversationIdsOutside,
  conversationScope,
  loadConversationId,
  loadSession,
  needsRefresh,
  saveConversationId,
  saveSession,
  tokenExpiresAt,
} from "./session";

function jwt(payload: object): string {
  const encode = (value: object) => btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${encode({ alg: "HS256" })}.${encode(payload)}.signature`;
}

describe("visitor token expiry", () => {
  it("reads exp from the token", () => {
    expect(tokenExpiresAt(jwt({ exp: 1_700_000_000 }))).toBe(1_700_000_000_000);
    expect(tokenExpiresAt("not-a-jwt")).toBeNull();
  });

  it("refreshes within five minutes of expiry, or when expiry is unknown", () => {
    const now = 1_700_000_000_000;

    expect(needsRefresh(jwt({ exp: now / 1000 + 3600 }), now)).toBe(false);
    expect(needsRefresh(jwt({ exp: now / 1000 + 120 }), now)).toBe(true);
    expect(needsRefresh("not-a-jwt", now)).toBe(true);
  });
});

describe("session storage", () => {
  it("is kept per widget key and cleared together with every remembered conversation", () => {
    const session = { token: "t", refreshToken: "r", visitor: { visitorId: "v", email: "v@example.com" } };
    saveSession("pk_a", session);
    saveConversationId("pk_a", "default", "conversation-1");
    saveConversationId("pk_a", "prompt-x", "conversation-2");

    expect(loadSession("pk_a")).toEqual(session);
    expect(loadSession("pk_b")).toBeNull();
    expect(loadConversationId("pk_a", "default")).toBe("conversation-1");
    expect(loadConversationId("pk_a", "prompt-x")).toBe("conversation-2");

    clearSession("pk_a");

    expect(loadSession("pk_a")).toBeNull();
    expect(loadConversationId("pk_a", "default")).toBeNull();
    expect(loadConversationId("pk_a", "prompt-x")).toBeNull();
  });

  it("forgets one scope's conversation without touching the others", () => {
    saveConversationId("pk_c", "default", "conversation-1");
    saveConversationId("pk_c", "prompt-x", "conversation-2");

    saveConversationId("pk_c", "prompt-x", null);

    expect(loadConversationId("pk_c", "default")).toBe("conversation-1");
    expect(loadConversationId("pk_c", "prompt-x")).toBeNull();
  });
});

describe("guest sessions", () => {
  it("stores a guest and forgets every conversation on end, remembering only the email", () => {
    const guest: Session = { token: "guest-token", refreshToken: "guest-refresh", visitor: { visitorId: "guest_1", email: "guest@example.com", kind: "guest" } };
    saveSession("guest-key", guest);
    saveConversationId("guest-key", "default", "one");
    saveConversationId("guest-key", "prompt-x", "two");
    expect(loadSession("guest-key")).toEqual(guest);
    expect(endLocalSession("guest-key", guest)).toBe("guest@example.com");
    expect(loadSession("guest-key")).toBeNull();
    expect(loadConversationId("guest-key", "default")).toBeNull();
    expect(loadConversationId("guest-key", "prompt-x")).toBeNull();
    expect(loadGuestEmail("guest-key")).toBe("guest@example.com");
    expect(loadGuestEmail("other-key")).toBe("");
  });

  it("returns legacy Google sessions to sign-in, not the guest ended card", () => {
    const google = { token: "t", visitor: { visitorId: "google", email: "google@example.com" } };
    saveSession("google-key", google);
    expect(endLocalSession("google-key", google)).toBeNull();
    expect(loadGuestEmail("google-key")).toBe("");
    expect(loadSession("google-key")).toBeNull();
  });
});

describe("conversationIdsOutside", () => {
  it("lists the conversations other chats on the site are using", () => {
    saveConversationId("pk_d", "default", "plain");
    saveConversationId("pk_d", "prompt-a", "section-a");
    saveConversationId("pk_d", "prompt-b", "section-b");

    expect(conversationIdsOutside("pk_d", "default")).toEqual(new Set(["section-a", "section-b"]));
    expect(conversationIdsOutside("pk_d", "prompt-a")).toEqual(new Set(["plain", "section-b"]));
  });
});

describe("conversationScope", () => {
  it("gives each prompt a stable scope of its own, and plain chats the default one", () => {
    expect(conversationScope(undefined)).toBe("default");
    expect(conversationScope("About Huila")).toBe(conversationScope("About Huila"));
    expect(conversationScope("About Huila")).not.toBe(conversationScope("About Yirgacheffe"));
    expect(conversationScope("About Huila")).toMatch(/^prompt-[0-9a-z]+$/);
  });
});
