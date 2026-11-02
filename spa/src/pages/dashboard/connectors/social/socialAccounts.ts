import type { SocialAccount } from "../../../../types/connectors";

const DAY_MS = 24 * 60 * 60 * 1000;
/** How long before a token runs out the page starts saying so; the API's own warning window. */
const WARN_DAYS = 14;

/** What to tell the person about an account's token: nothing while it is healthy and far from running out. */
export function accountNote(account: SocialAccount, now: Date = new Date()): string | null {
  if (account.status === "needs_reconnect") {
    // Why, when the network said (a refused token, or access removed in the network's settings)
    const why = account.last_error?.trim().replace(/\.$/, "");
    return `${why ? `${why}. ` : ""}Sign in again to keep posting to this account.`;
  }
  if (!account.token_expires_at) return null;
  const days = Math.ceil((new Date(account.token_expires_at).getTime() - now.getTime()) / DAY_MS);
  if (days > WARN_DAYS) return null;
  if (days <= 0) return "Sign-in expires today.";
  return `Sign-in expires in ${days} ${days === 1 ? "day" : "days"}.`;
}

/** The result parameters the OAuth return leaves in the URL, as something to tell the person. */
export function connectionOutcome(
  params: URLSearchParams,
  networks: { key: string; display_name: string }[]
): { kind: "success" | "error"; message: string } | null {
  const outcome = params.get("social_oauth");
  // The shared return step could not finish the sign-in at all (its link expired or was altered)
  if (!outcome && params.get("skill_oauth") === "error") {
    return { kind: "error", message: "The sign-in link expired. Connect again." };
  }
  if (!outcome) return null;
  const network = networks.find((item) => item.key === params.get("network"))?.display_name ?? "the account";
  if (outcome === "success") {
    // One sign-in can connect several Pages
    const added = (params.get("social_account_ids") ?? "").split(",").filter(Boolean).length;
    const message = added > 1 ? `${network} is connected: ${added} accounts added.` : `${network} is connected.`;
    return { kind: "success", message };
  }
  // The network's own explanation and what to do about it ("No Page was shared with InnoMight Labs. Connect again…")
  const detail = params.get("detail")?.trim();
  if (detail) return { kind: "error", message: `Could not connect ${network}. ${detail}` };
  const reasons: Record<string, string> = {
    cancelled: "the sign-in was cancelled",
    not_allowed: "only an account admin can connect accounts",
    invalid_state: "the sign-in link expired or belongs to someone else",
    no_accounts: "that sign-in gave access to nothing it can post as. Choose at least one Page you can create posts on",
  };
  return { kind: "error", message: `Could not connect ${network}: ${reasons[params.get("reason") ?? ""] ?? "something went wrong, try again"}.` };
}
