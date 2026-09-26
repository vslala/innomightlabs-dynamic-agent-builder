import { useEffect, useState } from "react";
import type { Dispatch, FormEvent, ReactNode, SetStateAction } from "react";
import { FileUp, Globe, KeyRound, Minus, Plus, RefreshCw, Server, Terminal } from "lucide-react";

import {
  Button,
  Checkbox,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from "../../../components/ui";
import { connectorApiService } from "../../../services/connectors";
import type { MCPConnection, MCPOAuthDeliveryKind, MCPStdioPackage } from "../../../types/connectors";
import { Field, Hint } from "./connectorUi";
import {
  DELIVERY_OPTIONS,
  buildCreateRequest,
  buildUpdateRequest,
  emptyEnvRow,
  emptyMCPForm,
  formFromConnection,
  newRowId,
  type MCPEnvRow,
  type MCPFormState,
} from "./mcpConnectionForm";

interface CustomMCPDialogProps {
  editing: MCPConnection | null;
  onClose: () => void;
  onSaved: () => Promise<void>;
}

/** Hand-configured MCP connector: a remote Streamable HTTP server or a hosted stdio package. */
export function CustomMCPDialog({ editing, onClose, onSaved }: CustomMCPDialogProps) {
  const [form, setForm] = useState<MCPFormState>(() => (editing ? formFromConnection(editing) : emptyMCPForm));
  const [saving, setSaving] = useState(false);
  const [fetchingAuth, setFetchingAuth] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [packages, setPackages] = useState<MCPStdioPackage[] | null>(null);

  const isStdio = form.transport === "stdio";
  const update = (changes: Partial<MCPFormState>) => setForm((current) => ({ ...current, ...changes }));

  useEffect(() => {
    if (!isStdio || packages !== null) return;
    connectorApiService
      .listMCPStdioPackages()
      .then(setPackages)
      .catch((err: unknown) => {
        setPackages([]);
        setError(err instanceof Error ? err.message : "Failed to load hosted packages.");
      });
  }, [isStdio, packages]);

  const close = () => {
    if (!saving) onClose();
  };

  const save = async () => {
    if (editing) {
      const result = buildUpdateRequest(form, editing);
      if (!result.ok) return result.error;
      await connectorApiService.updateMCPConnection(editing.mcp_id, result.request);
      return null;
    }
    const result = buildCreateRequest(form);
    if (!result.ok) return result.error;
    const saved = await connectorApiService.createMCPConnection(result.request);
    // A hosted server without sign-in can start right away, so its first tool call is warm.
    if (saved.transport === "stdio" && saved.auth_type !== "oauth") {
      await connectorApiService.restartMCPRuntime(saved.mcp_id).catch(() => undefined);
    }
    return null;
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const invalid = await save();
      if (invalid) {
        setError(invalid);
        return;
      }
      await onSaved();
    } catch (err) {
      console.error("Error saving MCP connector:", err);
      setError(err instanceof Error ? err.message : "Failed to save MCP connector.");
    } finally {
      setSaving(false);
    }
  };

  const fetchAuth = async () => {
    const source = isStdio ? form.issuerUrl.trim() : form.serverUrl.trim();
    if (!source) {
      setError(isStdio ? "Enter the authorization server URL first." : "Enter the MCP server URL before fetching OAuth details.");
      return;
    }
    setFetchingAuth(true);
    setError(null);
    try {
      const details = await connectorApiService.discoverMCPOAuth(isStdio ? { issuer_url: source } : { server_url: source });
      update({
        authType: "oauth",
        authorizationUrl: details.authorization_url,
        tokenUrl: details.token_url,
        clientId: details.client_id,
        clientSecret: details.client_secret,
        scope: details.scope || form.scope,
        resourceUrl: isStdio ? "" : details.resource_url,
        clientRegistration: details.client_registration,
      });
      if (!details.client_id) {
        setError("OAuth endpoints were found. This server did not auto-register a client, so enter the client ID manually.");
      }
    } catch (err) {
      console.error("Error fetching MCP OAuth details:", err);
      setError(err instanceof Error ? err.message : "Failed to fetch MCP OAuth details.");
    } finally {
      setFetchingAuth(false);
    }
  };

  const keepHint = Boolean(editing && editing.auth_type === "oauth");

  return (
    <Dialog open onOpenChange={(open) => !open && close()}>
      <DialogContent style={{ maxWidth: "38rem", maxHeight: "90vh", overflowY: "auto" }}>
        <DialogHeader>
          <DialogTitle>{editing ? "Edit MCP connector" : "Add MCP connector"}</DialogTitle>
          <DialogDescription>
            Connect a remote Streamable HTTP server, or host a stdio server package on InnoMight Labs.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void submit(event)} style={{ display: "grid", gap: "1rem" }}>
          <Field label="Name" htmlFor="mcp-name">
            <Input
              id="mcp-name"
              value={form.name}
              placeholder={isStdio ? "Google Ads" : "Ahrefs SEO"}
              onChange={(event) => update({ name: event.target.value })}
              required
            />
          </Field>

          <div style={{ display: "grid", gap: "0.75rem" }}>
            <Label>Server</Label>
            <ToggleRow
              options={[
                { value: "streamable_http", label: "Remote (HTTP)", icon: <Globe className="h-4 w-4" /> },
                { value: "stdio", label: "Hosted (stdio)", icon: <Terminal className="h-4 w-4" /> },
              ]}
              value={form.transport}
              disabled={Boolean(editing)}
              onChange={(transport) =>
                update({
                  transport: transport as MCPFormState["transport"],
                  authType: transport === "stdio" ? "none" : "api_key",
                })
              }
            />
            {editing && <Hint>The server type can't change. Create a new connector to switch.</Hint>}
          </div>

          {isStdio ? (
            <StdioFields form={form} packages={packages} update={update} editing={editing} />
          ) : (
            <Field label="Server URL" htmlFor="mcp-server-url">
              <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: "0.75rem" }}>
                <Input
                  id="mcp-server-url"
                  value={form.serverUrl}
                  placeholder="https://example.com/mcp"
                  onChange={(event) => update({ serverUrl: event.target.value })}
                  required
                />
                <Button type="button" variant="outline" onClick={() => void fetchAuth()} disabled={fetchingAuth || !form.serverUrl.trim()}>
                  <RefreshCw className="h-4 w-4" />
                  {fetchingAuth ? "Fetching..." : "Fetch auth"}
                </Button>
              </div>
            </Field>
          )}

          <div style={{ display: "grid", gap: "0.75rem" }}>
            <Label>Authentication</Label>
            <ToggleRow
              options={
                isStdio
                  ? [
                      { value: "none", label: "Environment", icon: <Server className="h-4 w-4" /> },
                      { value: "oauth", label: "OAuth sign-in", icon: <Globe className="h-4 w-4" /> },
                    ]
                  : [
                      { value: "none", label: "None", icon: <Server className="h-4 w-4" /> },
                      { value: "api_key", label: "API key", icon: <KeyRound className="h-4 w-4" /> },
                      { value: "oauth", label: "OAuth", icon: <Globe className="h-4 w-4" /> },
                    ]
              }
              value={form.authType}
              onChange={(authType) => update({ authType: authType as MCPFormState["authType"] })}
            />
            {isStdio && form.authType === "none" && (
              <Hint>Credentials go in the environment above. Mark them secret so they are never shown again.</Hint>
            )}
          </div>

          {!isStdio && form.authType === "api_key" && <HeaderFields form={form} setForm={setForm} editing={editing} />}

          {form.authType === "oauth" && (
            <div style={{ display: "grid", gap: "0.875rem" }}>
              {isStdio && (
                <Field label="Authorization server URL" htmlFor="mcp-oauth-issuer-url">
                  <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: "0.75rem" }}>
                    <Input
                      id="mcp-oauth-issuer-url"
                      value={form.issuerUrl}
                      placeholder="https://auth.provider.example"
                      onChange={(event) => update({ issuerUrl: event.target.value })}
                    />
                    <Button type="button" variant="outline" onClick={() => void fetchAuth()} disabled={fetchingAuth || !form.issuerUrl.trim()}>
                      <RefreshCw className="h-4 w-4" />
                      {fetchingAuth ? "Fetching..." : "Fetch auth"}
                    </Button>
                  </div>
                  <Hint>Optional. Fills in the endpoints, and registers a client when the server supports it.</Hint>
                </Field>
              )}
              <OAuthFields form={form} update={update} keepHint={keepHint} editing={editing} isStdio={isStdio} />
              {isStdio && <DeliveryFields form={form} update={update} />}
            </div>
          )}

          <label
            style={{
              display: "flex",
              gap: "0.75rem",
              alignItems: "center",
              padding: "0.875rem",
              border: "1px solid var(--border-subtle)",
              borderRadius: "0.5rem",
              background: "rgba(255,255,255,0.03)",
            }}
          >
            <Checkbox checked={form.enabled} onChange={(event) => update({ enabled: event.target.checked })} />
            <span style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
              <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>Enabled</span>
              <span style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                Disabled MCPs stay configured but cannot be enabled by agents.
              </span>
            </span>
          </label>
          {error && <div style={{ color: "var(--error)", fontSize: "0.875rem" }}>{error}</div>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={close} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" disabled={saving}>
              <KeyRound className="h-4 w-4" />
              {saving ? "Saving..." : editing ? "Save connector" : "Create connector"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ToggleRow({
  options,
  value,
  onChange,
  disabled = false,
}: {
  options: { value: string; label: string; icon: ReactNode }[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${options.length}, 1fr)`, gap: "0.75rem" }}>
      {options.map((option) => (
        <Button
          key={option.value}
          type="button"
          variant={value === option.value ? "default" : "outline"}
          onClick={() => onChange(option.value)}
          disabled={disabled && value !== option.value}
        >
          {option.icon}
          {option.label}
        </Button>
      ))}
    </div>
  );
}

function StdioFields({
  form,
  packages,
  update,
  editing,
}: {
  form: MCPFormState;
  packages: MCPStdioPackage[] | null;
  update: (changes: Partial<MCPFormState>) => void;
  editing: MCPConnection | null;
}) {
  const storedNames = new Set((editing?.stdio?.env ?? []).map((variable) => variable.name));
  const setRow = (id: string, changes: Partial<MCPEnvRow>) =>
    update({ envRows: form.envRows.map((row) => (row.id === id ? { ...row, ...changes } : row)) });

  return (
    <div style={{ display: "grid", gap: "0.875rem" }}>
      <Field label="Package" htmlFor="mcp-stdio-package">
        <Select value={form.stdioPackage} onValueChange={(stdioPackage) => update({ stdioPackage })}>
          <SelectTrigger id="mcp-stdio-package">
            <SelectValue placeholder={packages === null ? "Loading packages..." : "Choose a hosted package"} />
          </SelectTrigger>
          <SelectContent>
            {(packages ?? []).map((item) => (
              <SelectItem key={item.key} value={item.key} disabled={!item.installed}>
                {item.key} ({item.entrypoint})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Hint>Only packages reviewed and baked into the InnoMight Labs runtime can be hosted.</Hint>
      </Field>
      <Field label="Arguments" htmlFor="mcp-stdio-args">
        <Textarea
          id="mcp-stdio-args"
          value={form.stdioArgs}
          rows={2}
          placeholder="One argument per line (optional)"
          onChange={(event) => update({ stdioArgs: event.target.value })}
        />
      </Field>
      <div style={{ display: "grid", gap: "0.75rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "center" }}>
          <Label>Environment</Label>
          <Button type="button" variant="outline" size="sm" onClick={() => update({ envRows: [...form.envRows, emptyEnvRow()] })}>
            <Plus className="h-4 w-4" />
            Add variable
          </Button>
        </div>
        {form.envRows.map((row, index) => (
          <EnvRowEditor
            key={row.id}
            row={row}
            index={index}
            stored={storedNames.has(row.name)}
            onChange={(changes) => setRow(row.id, changes)}
            onRemove={() => update({ envRows: form.envRows.filter((item) => item.id !== row.id) })}
          />
        ))}
        {form.envRows.length === 0 && <Hint>No environment variables yet.</Hint>}
      </div>
    </div>
  );
}

function EnvRowEditor({
  row,
  index,
  stored,
  onChange,
  onRemove,
}: {
  row: MCPEnvRow;
  index: number;
  stored: boolean;
  onChange: (changes: Partial<MCPEnvRow>) => void;
  onRemove: () => void;
}) {
  const inputId = `mcp-env-file-${row.id}`;
  const keepPlaceholder = stored && (row.secret || row.kind === "file") ? "Leave blank to keep the stored value" : "Value";

  return (
    <div style={{ display: "grid", gap: "0.5rem", padding: "0.75rem", border: "1px solid var(--border-subtle)", borderRadius: "0.5rem" }}>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.4fr) auto", gap: "0.75rem" }}>
        <Input
          value={row.name}
          placeholder="NAME"
          aria-label={`Variable ${index + 1} name`}
          onChange={(event) => onChange({ name: event.target.value })}
        />
        {row.kind === "file" ? (
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", minWidth: 0 }}>
            <input
              id={inputId}
              type="file"
              style={{ display: "none" }}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void file.text().then((value) => onChange({ value }));
              }}
            />
            <Button type="button" variant="outline" size="sm" onClick={() => document.getElementById(inputId)?.click()}>
              <FileUp className="h-4 w-4" />
              Upload
            </Button>
            <span style={{ color: "var(--text-muted)", fontSize: "0.8125rem", overflow: "hidden", textOverflow: "ellipsis" }}>
              {row.value ? `${row.value.length} bytes loaded` : stored ? "Stored" : "No file"}
            </span>
          </div>
        ) : (
          <Input
            type={row.secret ? "password" : "text"}
            value={row.value}
            placeholder={keepPlaceholder}
            aria-label={`Variable ${index + 1} value`}
            onChange={(event) => onChange({ value: event.target.value })}
          />
        )}
        <Button type="button" variant="outline" size="icon" onClick={onRemove} aria-label={`Remove variable ${index + 1}`}>
          <Minus className="h-4 w-4" />
        </Button>
      </div>
      <div style={{ display: "flex", gap: "1rem", color: "var(--text-muted)", fontSize: "0.8125rem" }}>
        <label style={{ display: "flex", gap: "0.375rem", alignItems: "center" }}>
          <Checkbox checked={row.secret || row.kind === "file"} disabled={row.kind === "file"} onChange={(event) => onChange({ secret: event.target.checked })} />
          Secret
        </label>
        <label style={{ display: "flex", gap: "0.375rem", alignItems: "center" }}>
          <Checkbox
            checked={row.kind === "file"}
            onChange={(event) => onChange({ kind: event.target.checked ? "file" : "value", value: "" })}
          />
          File (the server gets a path to it)
        </label>
      </div>
    </div>
  );
}

function HeaderFields({
  form,
  setForm,
  editing,
}: {
  form: MCPFormState;
  setForm: Dispatch<SetStateAction<MCPFormState>>;
  editing: MCPConnection | null;
}) {
  const setHeader = (id: string, field: "name" | "value", value: string) =>
    setForm((current) => ({
      ...current,
      headers: current.headers.map((header) => (header.id === id ? { ...header, [field]: value } : header)),
    }));

  return (
    <div style={{ display: "grid", gap: "0.75rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "center" }}>
        <Label>Auth headers</Label>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            setForm((current) => ({
              ...current,
              headers: [...current.headers, { id: newRowId("header"), name: "", value: "" }],
            }))
          }
        >
          <Plus className="h-4 w-4" />
          Add header
        </Button>
      </div>
      {form.headers.map((header, index) => (
        <div key={header.id} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.4fr) auto", gap: "0.75rem" }}>
          <Input
            value={header.name}
            placeholder="Authorization"
            aria-label={`Header ${index + 1} key`}
            onChange={(event) => setHeader(header.id, "name", event.target.value)}
          />
          <Input
            type="password"
            value={header.value}
            placeholder={editing ? "Leave blank to keep existing headers" : "Bearer ..."}
            aria-label={`Header ${index + 1} value`}
            onChange={(event) => setHeader(header.id, "value", event.target.value)}
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={() =>
              setForm((current) =>
                current.headers.length <= 1
                  ? current
                  : { ...current, headers: current.headers.filter((item) => item.id !== header.id) }
              )
            }
            disabled={form.headers.length === 1}
            aria-label={`Remove header ${index + 1}`}
          >
            <Minus className="h-4 w-4" />
          </Button>
        </div>
      ))}
      {editing && <Hint>Leave all header values blank to keep the current stored headers.</Hint>}
    </div>
  );
}

function OAuthFields({
  form,
  update,
  keepHint,
  editing,
  isStdio,
}: {
  form: MCPFormState;
  update: (changes: Partial<MCPFormState>) => void;
  keepHint: boolean;
  editing: MCPConnection | null;
  isStdio: boolean;
}) {
  const required = !editing || editing.auth_type !== "oauth";
  const keep = (what: string, fallback: string) => (editing ? `Leave blank to keep existing ${what}` : fallback);

  return (
    <>
      <Field label="Authorization URL" htmlFor="mcp-oauth-authorization-url">
        <Input
          id="mcp-oauth-authorization-url"
          value={form.authorizationUrl}
          placeholder={keep("URL", "https://provider.example/oauth/authorize")}
          onChange={(event) => update({ authorizationUrl: event.target.value })}
          required={required}
        />
      </Field>
      <Field label="Token URL" htmlFor="mcp-oauth-token-url">
        <Input
          id="mcp-oauth-token-url"
          value={form.tokenUrl}
          placeholder={keep("URL", "https://provider.example/oauth/token")}
          onChange={(event) => update({ tokenUrl: event.target.value })}
          required={required}
        />
      </Field>
      <Field label="Client ID" htmlFor="mcp-oauth-client-id">
        <Input
          id="mcp-oauth-client-id"
          value={form.clientId}
          placeholder={keep("client ID", "OAuth client ID")}
          onChange={(event) => update({ clientId: event.target.value, clientRegistration: "manual" })}
          required={required}
        />
      </Field>
      <Field label="Client secret" htmlFor="mcp-oauth-client-secret">
        <Input
          id="mcp-oauth-client-secret"
          type="password"
          value={form.clientSecret}
          placeholder={keep("client secret", "Optional OAuth client secret")}
          onChange={(event) => update({ clientSecret: event.target.value })}
        />
      </Field>
      <Field label="Scopes" htmlFor="mcp-oauth-scope">
        <Input id="mcp-oauth-scope" value={form.scope} placeholder="read write" onChange={(event) => update({ scope: event.target.value })} />
      </Field>
      {!isStdio && (
        <Field label="Resource URL" htmlFor="mcp-oauth-resource-url">
          <Input
            id="mcp-oauth-resource-url"
            value={form.resourceUrl}
            placeholder="Defaults to the canonical MCP server URL"
            onChange={(event) => update({ resourceUrl: event.target.value })}
          />
        </Field>
      )}
      {keepHint && <Hint>Leave OAuth fields blank to keep the current stored provider config.</Hint>}
    </>
  );
}

function DeliveryFields({ form, update }: { form: MCPFormState; update: (changes: Partial<MCPFormState>) => void }) {
  const changeKind = (kind: MCPOAuthDeliveryKind) => {
    const isDefault = DELIVERY_OPTIONS.some((option) => option.defaultEnv === form.deliveryEnvName);
    const next = DELIVERY_OPTIONS.find((option) => option.kind === kind);
    update({ deliveryKind: kind, deliveryEnvName: isDefault && next ? next.defaultEnv : form.deliveryEnvName });
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.3fr) minmax(0, 1fr)", gap: "0.75rem" }}>
      <Field label="Deliver credential as" htmlFor="mcp-oauth-delivery">
        <Select value={form.deliveryKind} onValueChange={(kind) => changeKind(kind as MCPOAuthDeliveryKind)}>
          <SelectTrigger id="mcp-oauth-delivery">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DELIVERY_OPTIONS.map((option) => (
              <SelectItem key={option.kind} value={option.kind}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <Field label="Env var" htmlFor="mcp-oauth-delivery-env">
        <Input
          id="mcp-oauth-delivery-env"
          value={form.deliveryEnvName}
          onChange={(event) => update({ deliveryEnvName: event.target.value })}
        />
      </Field>
    </div>
  );
}
