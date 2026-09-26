import { describe, expect, it } from "vitest";

import type { MCPConnection } from "../../../types/connectors";
import {
  argsFromText,
  buildCreateRequest,
  buildUpdateRequest,
  emptyMCPForm,
  formFromConnection,
  type MCPFormState,
} from "./mcpConnectionForm";

function form(overrides: Partial<MCPFormState>): MCPFormState {
  return { ...emptyMCPForm, ...overrides };
}

function connection(overrides: Partial<MCPConnection>): MCPConnection {
  return {
    mcp_id: "mcp-1",
    name: "Existing",
    server_url: "https://mcp.example/mcp",
    transport: "streamable_http",
    auth_type: "api_key",
    oauth_connected: false,
    enabled: true,
    created_at: "2026-09-26T00:00:00Z",
    setup_state: "ready",
    inputs: {},
    ...overrides,
  };
}

const stdioForm = form({
  name: "Hosted Ads",
  transport: "stdio",
  authType: "none",
  stdioPackage: "google_ads",
  stdioArgs: "--verbose\n\n  --json  ",
  envRows: [
    { id: "a", name: "GOOGLE_ADS_DEVELOPER_TOKEN", value: "dev", secret: true, kind: "value" },
    { id: "b", name: "LOGIN_CUSTOMER_ID", value: " 123 ", secret: false, kind: "value" },
    { id: "c", name: "", value: "", secret: false, kind: "value" },
  ],
});

describe("remote (HTTP) connectors", () => {
  it("builds an API key request", () => {
    const result = buildCreateRequest(
      form({ name: " Ahrefs ", serverUrl: "https://mcp.ahrefs.example", headers: [{ id: "h", name: "Authorization", value: "Bearer x" }] })
    );

    expect(result).toEqual({
      ok: true,
      request: {
        name: "Ahrefs",
        server_url: "https://mcp.ahrefs.example",
        enabled: true,
        auth_type: "api_key",
        api_key: { headers: [{ name: "Authorization", value: "Bearer x" }] },
      },
    });
  });

  it("supports servers without authentication", () => {
    const result = buildCreateRequest(form({ name: "Public", serverUrl: "https://public.example", authType: "none" }));

    expect(result.ok && result.request.auth_type).toBe("none");
  });

  it("requires complete headers and OAuth endpoints", () => {
    expect(buildCreateRequest(form({ name: "x", serverUrl: "https://x", headers: [{ id: "h", name: "A", value: "" }] }))).toEqual({
      ok: false,
      error: "Each auth header must include both key and value.",
    });
    expect(buildCreateRequest(form({ name: "x", serverUrl: "https://x", authType: "oauth" })).ok).toBe(false);
  });

  it("keeps stored headers when edit leaves them blank", () => {
    const result = buildUpdateRequest(form({ name: "Existing", serverUrl: "https://mcp.example/mcp" }), connection({}));

    expect(result).toEqual({
      ok: true,
      request: { name: "Existing", server_url: "https://mcp.example/mcp", enabled: true },
    });
  });

  it("keeps the stored OAuth provider when edit leaves it blank", () => {
    const editing = connection({ auth_type: "oauth" });

    const result = buildUpdateRequest(form({ name: "Existing", serverUrl: "https://mcp.example/mcp", authType: "oauth" }), editing);

    expect(result.ok && result.request.oauth).toBeUndefined();
  });
});

describe("hosted (stdio) connectors", () => {
  it("builds a stdio request and derives credential auth from secret rows", () => {
    const result = buildCreateRequest(stdioForm);

    expect(result).toEqual({
      ok: true,
      request: {
        name: "Hosted Ads",
        transport: "stdio",
        enabled: true,
        auth_type: "api_key",
        stdio: {
          package: "google_ads",
          args: ["--verbose", "--json"],
          env: [
            { name: "GOOGLE_ADS_DEVELOPER_TOKEN", value: "dev", secret: true, kind: "value" },
            { name: "LOGIN_CUSTOMER_ID", value: "123", secret: false, kind: "value" },
          ],
        },
      },
    });
  });

  it("treats uploaded files as secrets", () => {
    const result = buildCreateRequest(
      form({
        ...stdioForm,
        envRows: [{ id: "f", name: "GOOGLE_APPLICATION_CREDENTIALS", value: '{"a":1}\n', secret: false, kind: "file" }],
      })
    );

    expect(result.ok && result.request.stdio?.env[0]).toEqual({
      name: "GOOGLE_APPLICATION_CREDENTIALS",
      value: '{"a":1}\n',
      secret: true,
      kind: "file",
    });
    expect(result.ok && result.request.auth_type).toBe("api_key");
  });

  it("requires a package and values for new variables", () => {
    expect(buildCreateRequest(form({ ...stdioForm, stdioPackage: "" }))).toEqual({
      ok: false,
      error: "Choose a package for the stdio server.",
    });
    expect(
      buildCreateRequest(form({ ...stdioForm, envRows: [{ id: "a", name: "TOKEN", value: "", secret: true, kind: "value" }] }))
    ).toEqual({ ok: false, error: "Environment variables need values: TOKEN" });
  });

  it("signs in with OAuth and a delivery, without a resource indicator", () => {
    const result = buildCreateRequest(
      form({
        ...stdioForm,
        authType: "oauth",
        authorizationUrl: "https://idp.example/authorize",
        tokenUrl: "https://idp.example/token",
        clientId: "client",
        clientSecret: "secret",
        clientRegistration: "dynamic",
        deliveryKind: "access_token_env",
        deliveryEnvName: "ACCESS_TOKEN",
      })
    );

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.request.auth_type).toBe("oauth");
    expect(result.request.oauth).toEqual({
      authorization_url: "https://idp.example/authorize",
      token_url: "https://idp.example/token",
      client_id: "client",
      client_secret: "secret",
      scope: "",
      client_registration: "dynamic",
    });
    expect(result.request.oauth_delivery).toEqual({ kind: "access_token_env", env_name: "ACCESS_TOKEN" });
  });

  it("round-trips an existing stdio connector and keeps blank stored secrets", () => {
    const editing = connection({
      transport: "stdio",
      server_url: "",
      auth_type: "api_key",
      stdio: {
        package: "google_ads",
        args: ["--verbose"],
        env: [
          { name: "GOOGLE_ADS_DEVELOPER_TOKEN", kind: "value", secret: true, value: null },
          { name: "LOGIN_CUSTOMER_ID", kind: "value", secret: false, value: "123" },
        ],
      },
    });

    const restored = formFromConnection(editing);
    const result = buildUpdateRequest(restored, editing);

    expect(restored.stdioArgs).toBe("--verbose");
    expect(restored.envRows.map((row) => row.value)).toEqual(["", "123"]);
    expect(result).toEqual({
      ok: true,
      request: {
        name: "Existing",
        enabled: true,
        stdio: {
          package: "google_ads",
          args: ["--verbose"],
          env: [
            { name: "GOOGLE_ADS_DEVELOPER_TOKEN", value: "", secret: true, kind: "value" },
            { name: "LOGIN_CUSTOMER_ID", value: "123", secret: false, kind: "value" },
          ],
        },
      },
    });
  });

  it("keeps the stored OAuth provider but still sends the delivery", () => {
    const editing = connection({
      transport: "stdio",
      auth_type: "oauth",
      stdio: { package: "google_ads", args: [], env: [] },
      oauth_delivery: { kind: "google_authorized_user_file", env_name: "GOOGLE_APPLICATION_CREDENTIALS" },
    });

    const result = buildUpdateRequest(formFromConnection(editing), editing);

    expect(result.ok && result.request.oauth).toBeUndefined();
    expect(result.ok && result.request.oauth_delivery).toEqual({
      kind: "google_authorized_user_file",
      env_name: "GOOGLE_APPLICATION_CREDENTIALS",
    });
  });
});

describe("argsFromText", () => {
  it("reads one argument per line", () => {
    expect(argsFromText(" --a \n\n--b value\n")).toEqual(["--a", "--b value"]);
  });
});
