import { useCallback, useEffect, useRef, useState } from "react";
import { Plug } from "lucide-react";

import { Button } from "../ui";
import { builderApiService } from "../../services/builder/BuilderApiService";
import { connectOutcome } from "../../services/builder/connect";
import styles from "./ConnectAccountCard.module.css";

export interface ConnectRequestPayload {
  provider: string;
  title: string;
  description: string;
  conversation_id: string;
}

type Stage = "idle" | "starting" | "signing_in" | "failed";

/**
 * The system asking the person to connect an account (Tavily, Atlassian…) before Ila's plan. The sign-in runs in
 * a popup so the chat stays open; the popup's return page posts the result back (see OAuthPopupDone).
 */
export function ConnectAccountCard({
  request,
  onConnected,
  disabled,
}: {
  request: ConnectRequestPayload;
  onConnected: () => void;
  disabled?: boolean;
}) {
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState<string | null>(null);
  const [fallbackUrl, setFallbackUrl] = useState<string | null>(null);
  const done = useRef(false);

  const finish = useCallback(() => {
    if (done.current) return;
    done.current = true;
    onConnected();
  }, [onConnected]);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const outcome = connectOutcome(event, window.location.origin);
      if (!outcome) return;
      if (outcome === "connected") {
        finish();
      } else {
        setStage("failed");
        setError("The sign-in didn't finish. Try again.");
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [finish]);

  const connect = async () => {
    setStage("starting");
    setError(null);
    try {
      const { authorize_url } = await builderApiService.connect(request.conversation_id, request.provider);
      if (!authorize_url) {
        finish();
        return;
      }
      const popup = window.open(authorize_url, "innomight-connect", "popup,width=520,height=720");
      if (!popup) setFallbackUrl(authorize_url);
      setStage("signing_in");
    } catch (e) {
      setStage("failed");
      setError(e instanceof Error ? e.message : "Couldn't start the sign-in.");
    }
  };

  return (
    <div className={styles.card}>
      <div className={styles.icon}>
        <Plug className="h-5 w-5" />
      </div>
      <div className={styles.body}>
        <div className={styles.title}>{request.title}</div>
        <p className={styles.description}>{request.description}</p>
        {error && <p className={styles.error}>{error}</p>}
        {fallbackUrl && (
          <p className={styles.description}>
            Your browser blocked the sign-in window.{" "}
            <a href={fallbackUrl} target="_blank" rel="noopener noreferrer">
              Open it in a new tab
            </a>
            .
          </p>
        )}
        <div className={styles.actions}>
          {stage === "signing_in" ? (
            // The popup may not be able to report back (some providers cut the link to this window); the plan checks.
            <Button size="sm" onClick={finish} disabled={disabled}>
              I've signed in
            </Button>
          ) : (
            <Button size="sm" onClick={connect} disabled={disabled || stage === "starting"}>
              {stage === "starting" ? "Opening sign-in…" : request.title}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
