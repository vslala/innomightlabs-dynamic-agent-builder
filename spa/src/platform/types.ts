/**
 * The ways running in a browser and running in the store apps differ, as small capability ports. Pages,
 * components and services depend on these, never on an adapter (see docs/LLD-mobile-ready-app.md, section 1).
 */

export type PlatformKind = "web" | "native";
export type LoginProvider = "google" | "cognito" | "apple";
export type Unsubscribe = () => void;
/** A path inside the signed-in app. Flows may only return into the dashboard. */
export type DashboardPath = `/dashboard${string}`;

export interface Platform {
  readonly kind: PlatformKind;
  readonly auth: AuthSession;
  readonly tokens: TokenStore;
  readonly links: Links;
  readonly storage: KeyValueStore;
  readonly lifecycle: Lifecycle;
  readonly files: Files;
  /** Null where push does not exist (the web): callers hide notification settings. */
  readonly push: PushChannel | null;
  readonly commerce: Commerce;
  /** Loads what the first render needs: stored values into memory, a fresh access token. Awaited once. */
  ready(): Promise<void>;
}

/** Starting and finishing sign-in. The adapter owns how a provider page opens and how the code is redeemed. */
export interface AuthSession {
  /** Web: this tab leaves for the provider. Native: the system browser opens; the app link finishes it. */
  begin(provider: LoginProvider, options?: { invitation?: string }): Promise<void>;
  /** Redeems the one-time code from `/login-success` (web) or the `auth` app link (native) for a session. */
  complete(code: string): Promise<void>;
  /** Ends the session on the server where one exists (native: revoke this device), then clears tokens. */
  end(): Promise<void>;
}

/** Credentials for API requests. Synchronous reads, because request headers are built synchronously. */
export interface TokenStore {
  accessToken(): string | null;
  /** A new access token after a 401. Single-flight: concurrent callers share one refresh. Null: signed out. */
  refresh(): Promise<string | null>;
  save(session: Session): Promise<void>;
  clear(): Promise<void>;
}

export interface Session {
  accessToken: string;
  /** Native only: kept in the Keychain or Keystore, never in web storage. */
  refreshToken?: string;
  /** Seconds until the access token expires, when the server says. */
  expiresIn?: number;
}

/** Ways out of the app and back in. */
export interface Links {
  /** The `return_to` a connect flow sends to the API, for a path in the app. */
  returnTo(path: DashboardPath): string;
  /**
   * A provider's sign-in or consent page that will come back through `returnTo`.
   * `popup`: the web opens a named popup instead of leaving the page (the chat card); native ignores it.
   * Resolves false when the page could not be opened (a blocked popup), so the caller can offer a link.
   */
  openAuthPage(url: string, options?: { popup?: boolean }): Promise<boolean>;
  /** An ordinary link that leaves the app: a new tab (web), the system browser (native). */
  openExternal(url: string): Promise<void>;
  /** Links that come back into the app. The web never calls the handler: its returns arrive as page loads. */
  onAppLink(handler: (link: AppLink) => void): Unsubscribe;
}

export type AppLink =
  | { kind: "login"; code: string | null; error: string | null }
  | { kind: "return"; path: DashboardPath; search: string };

/** Small, non-secret values (the active account, the device id, view choices). */
export interface KeyValueStore {
  /** Synchronous: served from memory, which `ready()` filled. */
  get(key: StorageKey): string | null;
  /** Writes memory now and the backing store in the background. */
  set(key: StorageKey, value: string): void;
  remove(key: StorageKey): void;
}

/** Every key the platform stores, in one place, so nothing is written under an ad hoc name. */
export type StorageKey = "active_account_id" | "device_id" | "pkce_verifier" | "conversations:view";

export interface Lifecycle {
  /** The app or tab came back to the foreground. Used to resync streams and refresh tokens. */
  onResume(handler: () => void): Unsubscribe;
}

export interface Files {
  /** A file the person keeps or sends on: a download (web), the share sheet (native). */
  saveOrShare(file: { data: Blob; filename: string }): Promise<void>;
}

export interface PushChannel {
  permission(): Promise<"granted" | "denied" | "prompt">;
  /** Asks the OS. Returns whether pushes may be shown. */
  requestPermission(): Promise<boolean>;
  /** Gets the FCM token and registers it as this device (`PUT /notifications/devices/{device_id}`). */
  register(): Promise<void>;
  /** On sign-out: `DELETE /notifications/devices/{device_id}`. */
  unregister(): Promise<void>;
  /** The person tapped a notification; `route` has already passed the `DashboardPath` check. */
  onOpen(handler: (route: DashboardPath) => void): Unsubscribe;
}

export interface Commerce {
  /** False in the store apps until in-app billing exists (Phase 4): no prices, purchase links or checkout. */
  readonly canSellSubscriptions: boolean;
}
