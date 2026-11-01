import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { platform, type AppLink } from "../../platform";
import { OAUTH_DONE_PATH, OAUTH_MESSAGE_TYPE, type OAuthPopupMessage } from "../../services/builder/connect";
import { completeOAuthHandoff, HANDOFF_PARAM } from "../../services/connectors/oauthCompletion";

/**
 * Acts on links coming back into the app (the store apps only: on the web `onAppLink` never fires, because
 * returns arrive as page loads). Mounted once, inside the router.
 *
 * - A finished sign-in: redeem the code, then the dashboard.
 * - The chat card's sign-in: complete it in place and tell the card, as the web's popup page would, so the open
 *   conversation stays where it is.
 * - Any other connect flow: load its page as the web does, so the page reads the result on mount.
 */
export function AppLinkRouter() {
  const navigate = useNavigate();

  useEffect(() => {
    const follow = async (link: AppLink) => {
      if (link.kind === "login") {
        if (!link.code) {
          navigate(`/login?error=${encodeURIComponent(link.error ?? "auth_failed")}`, { replace: true });
          return;
        }
        try {
          await platform().auth.complete(link.code);
          navigate("/dashboard", { replace: true });
        } catch {
          navigate("/login?error=auth_failed", { replace: true });
        }
        return;
      }

      if (link.path === OAUTH_DONE_PATH) {
        const completion = new URLSearchParams(link.search).get(HANDOFF_PARAM);
        const result = completion
          ? await completeOAuthHandoff(completion)
          : Object.fromEntries(new URLSearchParams(link.search));
        const message: OAuthPopupMessage = { type: OAUTH_MESSAGE_TYPE, result };
        window.postMessage(message, window.location.origin);
        return;
      }

      // A full load, like the web's return: a page already open would not read the new parameters.
      window.location.assign(`${link.path}${link.search}`);
    };

    return platform().links.onAppLink((link) => void follow(link));
  }, [navigate]);

  return null;
}
