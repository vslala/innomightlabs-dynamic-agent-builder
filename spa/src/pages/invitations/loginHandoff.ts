import { httpClient, setActiveAccountId } from "../../services/http";
import { authService } from "../../services/auth";

/** A null token means invitation navigation owns the continuation, not checkout. */
export async function redeemLoginSession(
  code: string,
  invitationContinuation: boolean,
  navigate: (path: string, options: { replace: boolean }) => void,
): Promise<string | null> {
  const { token } = await httpClient.post<{ token: string }>("/auth/session", { code }, { skipAuth: true });
  authService.setToken(token);
  setActiveAccountId(null);
  if (invitationContinuation) {
    navigate("/invitations/accept", { replace: true });
    return null;
  }
  return token;
}
