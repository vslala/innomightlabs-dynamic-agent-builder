import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { History, LogOut, SquarePen } from "lucide-react";

import { envelope, isEmbedMessage, type EmbedConfig, type FrameToHostMessage } from "../shared/protocol";
import { SignedOutError, WidgetApi, signInWithPopup } from "./api";
import type { Bootstrap } from "./bootstrap";
import { Composer } from "./components/Composer";
import { ConversationList } from "./components/ConversationList";
import { Header } from "./components/Header";
import { LoginPanel } from "./components/LoginPanel";
import { MessageList } from "./components/MessageList";
import { clearSession, loadSession, needsRefresh, saveSession, tokenExpiresAt, type Session } from "./session";
import { useChat, type ChatOptions } from "./useChat";

interface AppProps {
  bootstrap: Bootstrap;
  config: EmbedConfig;
}

/**
 * Whether the visitor can see the chat. A floating chat is seen once its panel opens. An inline
 * chat is seen once the iframe scrolls into the page's viewport: inside an iframe, an
 * IntersectionObserver with no root measures against the top-level viewport.
 */
function useSeenByVisitor(mode: EmbedConfig["mode"]): [boolean, () => void] {
  // Without IntersectionObserver there's no way to tell, so an inline chat counts as seen.
  const [seen, setSeen] = useState(() => mode === "inline" && typeof IntersectionObserver === "undefined");
  const markSeen = useCallback(() => setSeen(true), []);

  useEffect(() => {
    if (mode !== "inline" || seen) return;
    const observer = new IntersectionObserver((entries) => entries.some((entry) => entry.isIntersecting) && markSeen(), {
      threshold: 0.25,
    });
    observer.observe(document.documentElement);
    return () => observer.disconnect();
  }, [mode, seen, markSeen]);

  return [seen, markSeen];
}

function postToHost(message: FrameToHostMessage): void {
  // The parent's origin isn't known in advance; frame-ancestors already limits who the parent can be,
  // and these messages carry nothing private.
  if (window.parent !== window) window.parent.postMessage(envelope(message), "*");
}

export function App({ bootstrap, config }: AppProps) {
  const publicKey = bootstrap.public_key;
  const [session, setSession] = useState<Session | null>(() => loadSession(publicKey));
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [signInError, setSignInError] = useState<string | null>(null);
  const sessionRef = useRef(session);
  const refreshRef = useRef<Promise<string> | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const [isSeen, markSeen] = useSeenByVisitor(config.mode);

  const adoptSession = useCallback(
    (next: Session | null) => {
      sessionRef.current = next;
      setSession(next);
      if (next) saveSession(publicKey, next);
      else clearSession(publicKey);
    },
    [publicKey]
  );

  const signOut = useCallback(() => {
    const refreshToken = sessionRef.current?.refreshToken;
    if (refreshToken) void WidgetApi.revoke(publicKey, refreshToken).catch(() => undefined);
    adoptSession(null);
  }, [adoptSession, publicKey]);

  const api = useMemo(
    () =>
      new WidgetApi(publicKey, async () => {
        const current = sessionRef.current;
        if (!current) throw new SignedOutError("Please sign in.");
        if (!needsRefresh(current.token)) return current.token;

        const stillValid = (tokenExpiresAt(current.token) ?? 0) > Date.now();
        if (!current.refreshToken) {
          if (stillValid) return current.token;
          throw new SignedOutError("Your sign-in has expired.");
        }

        refreshRef.current ??= WidgetApi.refresh(publicKey, current.refreshToken)
          .then((refreshed) => {
            adoptSession(refreshed);
            return refreshed.token;
          })
          .catch((err) => {
            if (stillValid) return current.token;
            throw err;
          })
          .finally(() => {
            refreshRef.current = null;
          });
        return refreshRef.current;
      }),
    [publicKey, adoptSession]
  );

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.source !== window.parent || !isEmbedMessage(event.data)) return;
      if (event.data.type === "open") {
        markSeen();
        composerRef.current?.focus({ preventScroll: true });
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && config.mode === "floating") postToHost({ type: "close" });
    };

    window.addEventListener("message", onMessage);
    window.addEventListener("keydown", onKeyDown);
    postToHost({ type: "ready" });
    return () => {
      window.removeEventListener("message", onMessage);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [config.mode, markSeen]);

  const signIn = async () => {
    setIsSigningIn(true);
    setSignInError(null);
    try {
      adoptSession(await signInWithPopup(publicKey));
    } catch (err) {
      setSignInError(err instanceof Error ? err.message : "Sign-in failed. Please try again.");
    } finally {
      setIsSigningIn(false);
    }
  };

  const onClose = config.mode === "floating" ? () => postToHost({ type: "close" }) : undefined;
  const greeting = config.greeting || `Hi! I'm ${bootstrap.agent_name}. How can I help you today?`;

  return (
    <div className="ie-app">
      {session ? (
        <ChatScreen
          key={session.visitor.visitorId}
          api={api}
          bootstrap={bootstrap}
          session={session}
          greeting={greeting}
          placeholder={config.placeholder || "Write a message…"}
          chatOptions={{
            prompt: config.prompt,
            promptLabel: config.promptLabel,
            autoPrompt: config.autoPrompt,
            isVisible: isSeen,
          }}
          composerRef={composerRef}
          onSignOut={signOut}
          onClose={onClose}
        />
      ) : (
        <>
          <Header agentName={bootstrap.agent_name} subtitle="AI assistant" onClose={onClose} />
          <LoginPanel
            agentName={bootstrap.agent_name}
            description={bootstrap.agent_description}
            greeting={greeting}
            pendingQuestion={config.promptLabel || config.prompt}
            answersOnSignIn={config.autoPrompt !== false}
            isSigningIn={isSigningIn}
            error={signInError}
            onSignIn={signIn}
          />
        </>
      )}
      <Footer />
    </div>
  );
}

interface ChatScreenProps {
  api: WidgetApi;
  bootstrap: Bootstrap;
  session: Session;
  greeting: string;
  placeholder: string;
  chatOptions: ChatOptions;
  composerRef: RefObject<HTMLTextAreaElement | null>;
  onSignOut: () => void;
  onClose?: () => void;
}

function ChatScreen({ api, bootstrap, session, greeting, placeholder, chatOptions, composerRef, onSignOut, onClose }: ChatScreenProps) {
  const chat = useChat(api, bootstrap.public_key, onSignOut, chatOptions);
  const [showHistory, setShowHistory] = useState(false);

  const newChat = () => {
    chat.startNewChat();
    setShowHistory(false);
    composerRef.current?.focus({ preventScroll: true });
  };

  const actions = (
    <>
      <button
        type="button"
        className="ie-icon-button"
        aria-label="Previous conversations"
        aria-pressed={showHistory}
        onClick={() => setShowHistory((open) => !open)}
      >
        <History aria-hidden="true" />
      </button>
      <button type="button" className="ie-icon-button" aria-label="New conversation" onClick={newChat}>
        <SquarePen aria-hidden="true" />
      </button>
    </>
  );

  return (
    <>
      <Header agentName={bootstrap.agent_name} subtitle="AI assistant" actions={actions} onClose={onClose} />

      {chat.error && (
        <p className="ie-alert ie-alert-banner" role="alert">
          {chat.error}
          <button type="button" className="ie-alert-dismiss" aria-label="Dismiss" onClick={chat.dismissError}>
            ×
          </button>
        </p>
      )}

      {showHistory ? (
        <div className="ie-history-panel">
          <ConversationList
            conversations={chat.conversations}
            currentId={chat.conversationId}
            onSelect={(id) => {
              setShowHistory(false);
              chat.openConversation(id);
            }}
          />
          <div className="ie-account">
            <span className="ie-account-email">Signed in as {session.visitor.email}</span>
            <button type="button" className="ie-link-button" onClick={onSignOut}>
              <LogOut aria-hidden="true" />
              Sign out
            </button>
          </div>
        </div>
      ) : (
        <>
          <MessageList
            agentName={bootstrap.agent_name}
            greeting={greeting}
            messages={chat.messages}
            streaming={chat.streaming}
            activeTool={chat.activeTool}
            pendingForm={chat.pendingForm}
            isSending={chat.isSending}
            isLoading={chat.isLoading}
            suggestion={chat.suggestion}
            onSubmitForm={chat.send}
          />
          <Composer ref={composerRef} placeholder={placeholder} disabled={chat.isSending} onSend={(content) => chat.send(content)} />
        </>
      )}
    </>
  );
}

function Footer() {
  return (
    <footer className="ie-footer">
      Powered by{" "}
      <a href="https://innomightlabs.com" target="_blank" rel="noopener noreferrer">
        InnomightLabs
      </a>
    </footer>
  );
}
