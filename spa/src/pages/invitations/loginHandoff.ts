import { platform } from "../../platform";

/** A null token means invitation navigation owns the continuation, not checkout. */
export async function redeemLoginSession(
  code: string,
  invitationContinuation: boolean,
  navigate: (path: string, options: { replace: boolean }) => void,
): Promise<string | null> {
  await platform().auth.complete(code);
  if (invitationContinuation) {
    navigate("/invitations/accept", { replace: true });
    return null;
  }
  return platform().tokens.accessToken();
}
