import { describe, expect, it } from "vitest";

import type { SocialAccount } from "../../../../types/connectors";
import { accountNote, connectionOutcome } from "./socialAccounts";

const NOW = new Date("2026-10-21T12:00:00Z");

function account(overrides: Partial<SocialAccount>): SocialAccount {
  return {
    social_account_id: "sa-1",
    network: "linkedin",
    handle: "Ada Lovelace",
    display_name: "Ada Lovelace",
    avatar_url: null,
    status: "active",
    token_expires_at: null,
    last_error: null,
    created_at: "2026-10-01T00:00:00Z",
    ...overrides,
  };
}

const inDays = (days: number) => new Date(NOW.getTime() + days * 24 * 60 * 60 * 1000).toISOString();

describe("accountNote", () => {
  it("says nothing while the token is healthy", () => {
    expect(accountNote(account({ token_expires_at: inDays(40) }), NOW)).toBeNull();
    expect(accountNote(account({ token_expires_at: null }), NOW)).toBeNull();
  });

  it("warns in the last two weeks", () => {
    expect(accountNote(account({ token_expires_at: inDays(14) }), NOW)).toBe("Sign-in expires in 14 days.");
    expect(accountNote(account({ token_expires_at: inDays(1) }), NOW)).toBe("Sign-in expires in 1 day.");
    expect(accountNote(account({ token_expires_at: new Date(NOW.getTime() + 3600_000).toISOString() }), NOW)).toBe(
      "Sign-in expires in 1 day."
    );
  });

  it("asks to sign in again once the account needs it", () => {
    expect(accountNote(account({ status: "needs_reconnect", token_expires_at: inDays(-2) }), NOW)).toBe(
      "Sign in again to keep posting to this account."
    );
  });

  it("says why it needs a new sign-in when the network said", () => {
    expect(accountNote(account({ status: "needs_reconnect", last_error: "Access was removed in Facebook Pages" }), NOW)).toBe(
      "Access was removed in Facebook Pages. Sign in again to keep posting to this account."
    );
  });
});

describe("connectionOutcome", () => {
  const networks = [{ key: "linkedin", display_name: "LinkedIn" }];

  it("ignores a page that was not returned to", () => {
    expect(connectionOutcome(new URLSearchParams("tab=social"), networks)).toBeNull();
  });

  it("says so when the sign-in could not be finished at all", () => {
    expect(connectionOutcome(new URLSearchParams("tab=social&skill_oauth=error"), networks)).toEqual({
      kind: "error",
      message: "The sign-in link expired. Connect again.",
    });
  });

  it("welcomes a connected account", () => {
    expect(connectionOutcome(new URLSearchParams("social_oauth=success&network=linkedin"), networks)).toEqual({
      kind: "success",
      message: "LinkedIn is connected.",
    });
  });

  it("counts the accounts when one sign-in added several", () => {
    const pages = [{ key: "facebook_page", display_name: "Facebook Pages" }];
    expect(
      connectionOutcome(new URLSearchParams("social_oauth=success&network=facebook_page&social_account_ids=a,b"), pages)?.message
    ).toBe("Facebook Pages is connected: 2 accounts added.");
  });

  it("explains a sign-in that granted nothing to post as", () => {
    expect(connectionOutcome(new URLSearchParams("social_oauth=error&network=linkedin&reason=no_accounts"), networks)?.message).toBe(
      "Could not connect LinkedIn: that sign-in gave access to nothing it can post as. Choose at least one Page you can create posts on."
    );
  });

  it("explains a refusal, and falls back for a reason it does not know", () => {
    expect(connectionOutcome(new URLSearchParams("social_oauth=error&network=linkedin&reason=cancelled"), networks)).toEqual({
      kind: "error",
      message: "Could not connect LinkedIn: the sign-in was cancelled.",
    });
    expect(connectionOutcome(new URLSearchParams("social_oauth=error&reason=boom"), networks)?.message).toBe(
      "Could not connect the account: something went wrong, try again."
    );
  });
});
