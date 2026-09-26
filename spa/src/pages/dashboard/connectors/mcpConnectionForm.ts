/**
 * Form state for hand-configured MCP connectors, and the requests it turns into.
 *
 * Kept free of React so the rules (what edit leaves untouched, what each transport needs) are testable.
 */

import type {
  CreateMCPConnectionRequest,
  MCPAuthType,
  MCPConnection,
  MCPOAuthDeliveryKind,
  MCPOAuthProviderConfig,
  MCPStdioConfig,
  MCPTransport,
  UpdateMCPConnectionRequest,
} from "../../../types/connectors";

export interface MCPHeaderRow {
  id: string;
  name: string;
  value: string;
}

export interface MCPEnvRow {
  id: string;
  name: string;
  value: string;
  secret: boolean;
  kind: "value" | "file";
}

export interface MCPFormState {
  name: string;
  transport: MCPTransport;
  serverUrl: string;
  // Stdio uses "none" for environment-only credentials; the request's auth type is derived from the rows.
  authType: MCPAuthType;
  headers: MCPHeaderRow[];
  authorizationUrl: string;
  tokenUrl: string;
  clientId: string;
  clientSecret: string;
  scope: string;
  resourceUrl: string;
  issuerUrl: string;
  clientRegistration: "manual" | "dynamic";
  stdioPackage: string;
  stdioArgs: string;
  envRows: MCPEnvRow[];
  deliveryKind: MCPOAuthDeliveryKind;
  deliveryEnvName: string;
  enabled: boolean;
}

export type MCPFormResult<T> = { ok: true; request: T } | { ok: false; error: string };

export const DELIVERY_OPTIONS: { kind: MCPOAuthDeliveryKind; label: string; defaultEnv: string }[] = [
  { kind: "access_token_env", label: "Access token in an env var", defaultEnv: "ACCESS_TOKEN" },
  {
    kind: "google_authorized_user_file",
    label: "Google credentials file (ADC)",
    defaultEnv: "GOOGLE_APPLICATION_CREDENTIALS",
  },
];

let rowCounter = 0;
export function newRowId(prefix: string): string {
  rowCounter += 1;
  return `${prefix}-${Date.now()}-${rowCounter}`;
}

export function emptyEnvRow(): MCPEnvRow {
  return { id: newRowId("env"), name: "", value: "", secret: false, kind: "value" };
}

export const emptyMCPForm: MCPFormState = {
  name: "",
  transport: "streamable_http",
  serverUrl: "",
  authType: "api_key",
  headers: [{ id: "header-1", name: "Authorization", value: "" }],
  authorizationUrl: "",
  tokenUrl: "",
  clientId: "",
  clientSecret: "",
  scope: "",
  resourceUrl: "",
  issuerUrl: "",
  clientRegistration: "manual",
  stdioPackage: "",
  stdioArgs: "",
  envRows: [],
  deliveryKind: "access_token_env",
  deliveryEnvName: "ACCESS_TOKEN",
  enabled: true,
};

export function formFromConnection(connection: MCPConnection): MCPFormState {
  const base: MCPFormState = {
    ...emptyMCPForm,
    name: connection.name,
    transport: connection.transport,
    serverUrl: connection.server_url,
    authType: connection.auth_type,
    enabled: connection.enabled,
  };
  if (connection.transport !== "stdio" || !connection.stdio) return base;

  return {
    ...base,
    authType: connection.auth_type === "oauth" ? "oauth" : "none",
    stdioPackage: connection.stdio.package,
    stdioArgs: connection.stdio.args.join("\n"),
    envRows: connection.stdio.env.map((variable) => ({
      id: newRowId("env"),
      name: variable.name,
      // Secret and file values are never returned; blank keeps the stored value.
      value: variable.value ?? "",
      secret: variable.secret,
      kind: variable.kind,
    })),
    deliveryKind: connection.oauth_delivery?.kind ?? emptyMCPForm.deliveryKind,
    deliveryEnvName: connection.oauth_delivery?.env_name ?? emptyMCPForm.deliveryEnvName,
  };
}

export function argsFromText(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function buildCreateRequest(form: MCPFormState): MCPFormResult<CreateMCPConnectionRequest> {
  const name = form.name.trim();
  if (form.transport === "stdio") return buildStdioCreate(form, name);

  const serverUrl = form.serverUrl.trim();
  if (!name || !serverUrl) return fail("Name and server URL are required.");
  const base = { name, server_url: serverUrl, enabled: form.enabled };

  if (form.authType === "none") return ok({ ...base, auth_type: "none" });
  if (form.authType === "api_key") {
    const headers = headerRows(form);
    if (headers.some((header) => !header.name || !header.value)) {
      return fail("Each auth header must include both key and value.");
    }
    if (headers.length === 0) return fail("At least one auth header is required for a new MCP connector.");
    return ok({ ...base, auth_type: "api_key", api_key: { headers } });
  }
  const oauth = httpOAuthConfig(form);
  if (!oauth.authorization_url || !oauth.token_url || !oauth.client_id) {
    return fail("Authorization URL, token URL, and client ID are required for OAuth MCP connectors.");
  }
  return ok({ ...base, auth_type: "oauth", oauth });
}

export function buildUpdateRequest(
  form: MCPFormState,
  editing: MCPConnection
): MCPFormResult<UpdateMCPConnectionRequest> {
  const name = form.name.trim();
  if (editing.transport === "stdio") return buildStdioUpdate(form, editing, name);

  const serverUrl = form.serverUrl.trim();
  if (!name || !serverUrl) return fail("Name and server URL are required.");
  const request: UpdateMCPConnectionRequest = { name, server_url: serverUrl, enabled: form.enabled };

  if (form.authType === "none") {
    return ok(editing.auth_type === "none" ? request : { ...request, auth_type: "none" });
  }
  if (form.authType === "api_key") {
    const headers = headerRows(form);
    const replaceHeaders = headers.some((header) => header.value);
    if (!replaceHeaders) {
      return editing.auth_type === "api_key"
        ? ok(request)
        : fail("At least one auth header is required when switching to API key authentication.");
    }
    if (headers.some((header) => !header.name || !header.value)) {
      return fail("Each auth header must include both key and value.");
    }
    return ok({ ...request, auth_type: "api_key", api_key: { headers } });
  }

  const oauth = httpOAuthConfig(form);
  const replaceOAuth = editing.auth_type !== "oauth" || Object.values(oauth).some(Boolean);
  if (!replaceOAuth) return ok(request);
  if (!oauth.authorization_url || !oauth.token_url || !oauth.client_id) {
    return fail("Authorization URL, token URL, and client ID are required for OAuth MCP connectors.");
  }
  return ok({ ...request, auth_type: "oauth", oauth });
}

function buildStdioCreate(form: MCPFormState, name: string): MCPFormResult<CreateMCPConnectionRequest> {
  if (!name) return fail("Name is required.");
  const stdio = stdioConfig(form, new Set());
  if (!stdio.ok) return stdio;

  const base = { name, transport: "stdio" as const, stdio: stdio.request, enabled: form.enabled };
  if (form.authType !== "oauth") {
    return ok({ ...base, auth_type: stdio.request.env.some((row) => row.secret) ? "api_key" : "none" });
  }
  const oauth = stdioOAuthConfig(form);
  if (!oauth.authorization_url || !oauth.token_url || !oauth.client_id) {
    return fail("Authorization URL, token URL, and client ID are required for OAuth sign-in.");
  }
  const delivery = deliveryFor(form);
  if (!delivery.ok) return delivery;
  return ok({ ...base, auth_type: "oauth", oauth, oauth_delivery: delivery.request });
}

function buildStdioUpdate(
  form: MCPFormState,
  editing: MCPConnection,
  name: string
): MCPFormResult<UpdateMCPConnectionRequest> {
  if (!name) return fail("Name is required.");
  const storedNames = new Set((editing.stdio?.env ?? []).map((variable) => variable.name));
  const stdio = stdioConfig(form, storedNames);
  if (!stdio.ok) return stdio;

  const request: UpdateMCPConnectionRequest = { name, enabled: form.enabled, stdio: stdio.request };
  if (form.authType !== "oauth") {
    const authType: MCPAuthType = stdio.request.env.some((row) => row.secret) ? "api_key" : "none";
    return ok(authType === editing.auth_type ? request : { ...request, auth_type: authType });
  }

  const delivery = deliveryFor(form);
  if (!delivery.ok) return delivery;
  const oauth = stdioOAuthConfig(form);
  const replaceOAuth =
    editing.auth_type !== "oauth" || Boolean(oauth.authorization_url || oauth.token_url || oauth.client_id);
  if (!replaceOAuth) return ok({ ...request, oauth_delivery: delivery.request });
  if (!oauth.authorization_url || !oauth.token_url || !oauth.client_id) {
    return fail("Authorization URL, token URL, and client ID are required for OAuth sign-in.");
  }
  return ok({ ...request, auth_type: "oauth", oauth, oauth_delivery: delivery.request });
}

function stdioConfig(form: MCPFormState, storedNames: Set<string>): MCPFormResult<MCPStdioConfig> {
  if (!form.stdioPackage) return fail("Choose a package for the stdio server.");
  const rows = form.envRows
    .map((row) => ({ ...row, name: row.name.trim() }))
    .filter((row) => row.name || row.value);
  if (rows.some((row) => !row.name)) return fail("Each environment variable needs a name.");
  const missing = rows.filter((row) => !row.value && !storedNames.has(row.name)).map((row) => row.name);
  if (missing.length > 0) return fail(`Environment variables need values: ${missing.join(", ")}`);
  return ok({
    package: form.stdioPackage,
    args: argsFromText(form.stdioArgs),
    env: rows.map(({ name, value, secret, kind }) => ({
      name,
      value: kind === "file" ? value : value.trim(),
      // File contents are credentials more often than not, so they are always kept secret.
      secret: secret || kind === "file",
      kind,
    })),
  });
}

function deliveryFor(form: MCPFormState): MCPFormResult<{ kind: MCPOAuthDeliveryKind; env_name: string }> {
  const envName = form.deliveryEnvName.trim();
  if (!envName) return fail("Choose the env var that receives the OAuth credential.");
  return ok({ kind: form.deliveryKind, env_name: envName });
}

function headerRows(form: MCPFormState) {
  return form.headers
    .map((header) => ({ name: header.name.trim(), value: header.value.trim() }))
    .filter((header) => header.name || header.value);
}

function httpOAuthConfig(form: MCPFormState): MCPOAuthProviderConfig {
  return {
    authorization_url: form.authorizationUrl.trim(),
    token_url: form.tokenUrl.trim(),
    client_id: form.clientId.trim(),
    client_secret: form.clientSecret.trim(),
    scope: form.scope.trim(),
    resource_url: form.resourceUrl.trim(),
  };
}

function stdioOAuthConfig(form: MCPFormState): MCPOAuthProviderConfig & { client_registration: "manual" | "dynamic" } {
  // Stdio servers have no URL of their own, so there is no RFC 8707 resource to send.
  return {
    authorization_url: form.authorizationUrl.trim(),
    token_url: form.tokenUrl.trim(),
    client_id: form.clientId.trim(),
    client_secret: form.clientSecret.trim(),
    scope: form.scope.trim(),
    client_registration: form.clientRegistration,
  };
}

function ok<T>(request: T): MCPFormResult<T> {
  return { ok: true, request };
}

function fail<T>(error: string): MCPFormResult<T> {
  return { ok: false, error };
}
