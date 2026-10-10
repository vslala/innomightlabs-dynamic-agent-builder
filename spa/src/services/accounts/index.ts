/**
 * Accounts the signed-in person belongs to, and which one requests act in.
 * See docs/LLD-shared-accounts-and-iam.md, "Account context and switching".
 */

import { getActiveAccountId, httpClient, setActiveAccountId } from "../http";

export type AccessSummary = "owner" | "admin" | "member";

export interface AccountMembership {
  account_id: string;
  name: string;
  access_summary: AccessSummary;
  membership_status: "active" | "suspended";
  joined_at: string;
  /** The account the API acts in for requests that don't name one. */
  active: boolean;
}

class AccountService {
  async list(): Promise<AccountMembership[]> {
    return httpClient.get<AccountMembership[]>("/accounts");
  }

  /** The account this tab acts in: its own choice if still valid, else the one the API picks. */
  current(accounts: AccountMembership[]): AccountMembership | undefined {
    const chosen = getActiveAccountId();
    return accounts.find((account) => account.account_id === chosen) ?? accounts.find((account) => account.active);
  }

  /** Act in another account: here at once, and remembered for the person's other devices. */
  async switchTo(accountId: string): Promise<void> {
    await httpClient.put<AccountMembership>("/accounts/active", { account_id: accountId });
    setActiveAccountId(accountId);
  }
}

export const accountService = new AccountService();
