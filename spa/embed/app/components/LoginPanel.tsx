import { useEffect, useRef, useState, type FormEvent } from "react";
import { GuestEntryError, WidgetApi } from "../api";
import { loadGuestEmail, type Session } from "../session";
import { scheduleGuestAcceptance, useDelayedPhase } from "../useDelayedPhase";
import { AgentAvatar } from "./Header";

interface LoginPanelProps {
  publicKey: string;
  allowGuests: boolean;
  timeoutMinutes?: number;
  onGuestSession: (session: Session) => void;
  agentName: string;
  description: string | null;
  greeting: string;
  /** The question this chat will answer as soon as the visitor signs in, if it has a default prompt. */
  pendingQuestion?: string;
  /** Whether that question is answered automatically after sign-in, or offered as a suggestion. */
  answersOnSignIn: boolean;
  isSigningIn: boolean;
  error: string | null;
  onSignIn: () => void;
}

export function LoginPanel({
  publicKey,
  allowGuests,
  timeoutMinutes,
  onGuestSession,
  agentName,
  description,
  greeting,
  pendingQuestion,
  answersOnSignIn,
  isSigningIn,
  error,
  onSignIn,
}: LoginPanelProps) {
  const [guestBusy, setGuestBusy] = useState(false);
  return (
    <div className="ie-login">
      <AgentAvatar name={agentName} large />
      <h2 className="ie-login-title">Chat with {agentName}</h2>
      {description && <p className="ie-login-description">{description}</p>}
      <div className="ie-bubble ie-bubble-assistant ie-login-greeting">{greeting}</div>
      {pendingQuestion && <div className="ie-bubble ie-bubble-user ie-login-question">{pendingQuestion}</div>}

      {error && (
        <p className="ie-alert" role="alert">
          {error}
        </p>
      )}

      {allowGuests && <GuestEntry publicKey={publicKey} timeoutMinutes={timeoutMinutes} disabled={isSigningIn}
        onBusy={setGuestBusy} onSession={onGuestSession} />}
      {allowGuests && <span className="ie-login-note">or</span>}
      <button type="button" className="ie-button ie-google" onClick={onSignIn} disabled={isSigningIn || guestBusy}>
        <GoogleMark />
        {isSigningIn ? "Waiting for Google…" : "Continue with Google"}
      </button>
      <p className="ie-login-note">
        {allowGuests ? "Sign in to keep your chats and pick up where you left off." : pendingQuestion && answersOnSignIn
          ? "Sign in and you'll get an answer straight away. Your conversations stay private to you."
          : "Signing in keeps your conversations private to you and lets you pick up where you left off."}
      </p>
    </div>
  );
}

function GuestEntry({ publicKey, timeoutMinutes, disabled, onBusy, onSession }: {
  publicKey: string; timeoutMinutes?: number; disabled: boolean;
  onBusy: (busy: boolean) => void; onSession: (session: Session) => void;
}) {
  const [email, setEmail] = useState(() => loadGuestEmail(publicKey));
  const [pending, setPending] = useState(false);
  const [accepted, setAccepted] = useState<Session | null>(null);
  const [error, setError] = useState<GuestEntryError | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);
  const phase = useDelayedPhase(pending);
  const busy = pending || accepted !== null;
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    if (!accepted) return;
    return scheduleGuestAcceptance(() => onSession(accepted));
  }, [accepted, onSession]);
  useEffect(() => {
    if (error) { input.current?.focus(); input.current?.select(); }
  }, [error]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (request.current || disabled || accepted) return;
    const controller = new AbortController();
    request.current = controller;
    setError(null);
    setPending(true);
    onBusy(true);
    try {
      const session = await WidgetApi.startGuest(publicKey, email.trim(), controller.signal);
      if (!controller.signal.aborted) setAccepted(session);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof GuestEntryError ? err : new GuestEntryError("We couldn't check that address. Please try again.", true));
      onBusy(false);
    } finally {
      if (!controller.signal.aborted) setPending(false);
      request.current = null;
    }
  };
  const checking = phase === "slow" || phase === "very-slow";
  return (
    <form className={`ie-guest-form${accepted ? " ie-guest-accepted" : ""}`} onSubmit={submit}>
      <label htmlFor="guest-email">Your email address</label>
      <div className={`${checking ? "ie-email-checking" : ""} ${error ? "ie-email-rejected" : ""}`}>
        <input ref={input} id="guest-email" type="email" autoComplete="email" required value={email}
          disabled={busy || disabled} aria-invalid={!!error} aria-describedby="guest-notice guest-status"
          onChange={(event) => setEmail(event.target.value)} />
      </div>
      <div id="guest-status" className="ie-guest-status" aria-live="polite" aria-atomic="true">
        {accepted ? "Email accepted. Opening your chat…" : error ? <p className="ie-alert">{error.message}</p>
          : phase === "very-slow" ? <p>Still checking — some mail servers take a moment.</p>
          : checking ? "Checking your email…" : null}
      </div>
      <button className="ie-button" type="submit" disabled={busy || disabled} aria-busy={pending}>
        {accepted ? <><span aria-hidden="true">✓</span> Email accepted</> : checking
          ? <><span className="ie-spinner" aria-hidden="true" /> Checking your email…</> : "Continue as guest"}
      </button>
      {error?.retryable && <button className="ie-link-button" type="submit" disabled={busy || disabled}>Try again</button>}
      <p id="guest-notice" className="ie-login-note">
        We'll email you a transcript of this chat when it ends. Use an address you own.
        {timeoutMinutes && timeoutMinutes > 0 ? ` Your chat ends after ${timeoutMinutes} minutes without messages.` : " Your chat ends after a period without messages."}
        {" "}It's then removed from this site; a private archive is retained under our{" "}
        <a href="https://innomightlabs.com/legal/privacy" target="_blank" rel="noopener noreferrer">Privacy Policy</a>.
        {" "}Email delivery is not guaranteed.
      </p>
    </form>
  );
}

function GoogleMark() {
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true" className="ie-google-mark">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}
