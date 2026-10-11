import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../../components/ui/button";
import { authService } from "../../services/auth";
import { HttpError } from "../../services/http";
import { invitationService, invitationErrorMessage, type InvitationPreview } from "../../services/iam/invitations";
import { acceptInvitation } from "./acceptInvitation";
import { captureInvitationToken, invitationLoginUrl } from "./continuation";
import styles from "./Invitations.module.css";

export function AcceptInvitationPage() {
  const navigate = useNavigate();
  const [bootstrap] = useState(() => captureInvitationToken(window.location, window.history, () => window.sessionStorage));
  const [preview, setPreview] = useState<InvitationPreview>();
  const [error, setError] = useState(bootstrap.error);
  const [loading, setLoading] = useState(Boolean(bootstrap.token));
  const [signedIn, setSignedIn] = useState(() => authService.isAuthenticated());
  const [pending, setPending] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const inFlight = useRef(false);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    if (!bootstrap.token) return;
    const controller = new AbortController();
    invitationService.preview(bootstrap.token, controller.signal).then(
      (result) => { if (!controller.signal.aborted) { setPreview(result); setLoading(false); } },
      (error: unknown) => { if (!controller.signal.aborted) { setError(invitationErrorMessage(error)); setLoading(false); } },
    );
    return () => controller.abort();
  }, [bootstrap.token, attempt]);

  async function accept() {
    if (!bootstrap.token || inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    setError(undefined);
    try {
      await acceptInvitation(bootstrap.token);
      if (mounted.current) navigate("/dashboard", { replace: true });
    } catch (error) {
      if (mounted.current) {
        if (error instanceof HttpError && error.status === 401) setSignedIn(false);
        setError(invitationErrorMessage(error));
      }
    } finally {
      inFlight.current = false;
      if (mounted.current) setPending(false);
    }
  }

  const joinable = preview?.status === "pending" || preview?.status === "accepted";
  return (
    <main className={styles.container}>
      <section className={styles.card} aria-labelledby="invitation-title" aria-busy={loading || pending}>
        <h1 id="invitation-title">Account invitation</h1>
        {loading && <p role="status">Loading invitation…</p>}
        {!bootstrap.token && !bootstrap.error && <p>This invitation link is missing. Reopen the link in your invitation email, or contact the account administrator for a new invitation.</p>}
        {error && <div role="alert"><p>{error}</p><p>If the invitation is invalid, expired or revoked, contact the account administrator to resend it. To use a different identity, sign in with the invited email.</p></div>}
        {bootstrap.token && error && !preview && <Button type="button" variant="outline" onClick={() => { setError(undefined); setLoading(true); setAttempt((value) => value + 1); }}>Retry</Button>}
        {preview && <>
          <p>You have been invited to <strong>{preview.account_name}</strong>.</p>
          <p>Invited email: <strong>{preview.email}</strong></p>
          <p>Expires: <time dateTime={preview.expires_at}>{preview.expires_at}</time></p>
          {!joinable && <p role="alert">This invitation is {preview.status}. Contact the account administrator to resend an invitation.</p>}
          {joinable && (signedIn ? <>
            <p>Accept with your signed-in identity. The server will verify that you are the invited recipient.</p>
            <div className={styles.actions}>
              <Button type="button" disabled={pending} onClick={() => { void accept(); }}>{pending ? "Accepting…" : "Accept invitation"}</Button>
              <Button type="button" variant="outline" disabled={pending} onClick={() => { authService.removeToken(); setSignedIn(false); setError(undefined); }}>Sign in with the invited email</Button>
            </div>
          </> : <>
            <p>Sign in with {preview.email} to continue. You will confirm acceptance after signing in.</p>
            <div className={styles.actions}>
              <Button asChild><a href={invitationLoginUrl("google", preview.login_context)}>Continue with Google</a></Button>
              <Button asChild variant="outline"><a href={invitationLoginUrl("cognito", preview.login_context)}>Continue with Cognito</a></Button>
            </div>
          </>)}
        </>}
      </section>
    </main>
  );
}
