import { useEffect, useState } from "react";

import { OAUTH_MESSAGE_TYPE, type OAuthPopupMessage } from "../../../services/builder/connect";

/**
 * Where a sign-in popup lands. OAuthReturn (around every dashboard page) has already completed the handoff and
 * put the result in the URL; this tells the chat that opened the popup, then closes.
 */
export function OAuthPopupDone() {
  const [canClose, setCanClose] = useState(true);
  const result = Object.fromEntries(new URLSearchParams(window.location.search));
  const succeeded = Object.entries(result).some(([key, value]) => key.endsWith("_oauth") && value === "success");

  useEffect(() => {
    const message: OAuthPopupMessage = { type: OAUTH_MESSAGE_TYPE, result };
    if (window.opener) {
      window.opener.postMessage(message, window.location.origin);
      window.close();
    }
    // Still here: no opener, or the browser kept the window open.
    setCanClose(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div style={{ padding: "3rem 1.5rem", textAlign: "center", color: "var(--text-primary)" }}>
      <h1 style={{ fontSize: "1.25rem", fontWeight: 600 }}>{succeeded ? "You're connected" : "Sign-in didn't finish"}</h1>
      {!canClose && (
        <p style={{ marginTop: "0.5rem", color: "var(--text-secondary)" }}>
          {succeeded
            ? "You can close this window and go back to your chat with Ada."
            : "Close this window and try again from your chat with Ada."}
        </p>
      )}
    </div>
  );
}
