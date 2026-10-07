import { useEffect, useState } from "react";
import { Check, Copy, Eye, EyeOff, Globe, Key, Plus, Trash2 } from "lucide-react";

import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../../../components/ui/dialog";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { Textarea } from "../../../components/ui/textarea";
import { apiKeyService, type ApiKeyResponse } from "../../../services/apikeys";
import { SecretKeysCard } from "./SecretKeysCard";
import { WidgetSnippets } from "./WidgetSnippets";
import { useAgentDetailContext } from "./types";
import styles from "./AgentApiKeysPage.module.css";

const guestHelp = "Visitors can chat without signing in by giving their email. When their session ends (this agent's session timeout), the chat is archived, a transcript email is attempted, and it's removed from the site. Guests can't use this agent's skills or shared tools. Applies to the iframe embed only; classic widget.js still requires Google sign-in.";

export function AgentApiKeysPage() {
  const { agent } = useAgentDetailContext();
  const [apiKeys, setApiKeys] = useState<ApiKeyResponse[]>([]);
  const [loadingApiKeys, setLoadingApiKeys] = useState(false);
  const [isCreateKeyDialogOpen, setIsCreateKeyDialogOpen] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyOrigins, setNewKeyOrigins] = useState("");
  const [newKeyAllowGuests, setNewKeyAllowGuests] = useState(false);
  const [updatingGuestKeyId, setUpdatingGuestKeyId] = useState<string | null>(null);
  const [guestUpdateError, setGuestUpdateError] = useState<{ keyId: string; message: string } | null>(null);
  const [isCreatingKey, setIsCreatingKey] = useState(false);
  const [createKeyError, setCreateKeyError] = useState<string | null>(null);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);
  const [isDeletingKey, setIsDeletingKey] = useState(false);
  const [copiedKeyId, setCopiedKeyId] = useState<string | null>(null);
  const [visibleKeyId, setVisibleKeyId] = useState<string | null>(null);
  const [revealedA2ASecret, setRevealedA2ASecret] = useState<{ keyId: string; secret: string } | null>(null);
  const [issuingA2AKeyId, setIssuingA2AKeyId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadApiKeys() {
      setLoadingApiKeys(true);
      try {
        const keys = await apiKeyService.listApiKeys(agent.agent_id);
        if (!cancelled) {
          setApiKeys(keys);
        }
      } catch (err) {
        console.error("Error loading API keys:", err);
      } finally {
        if (!cancelled) {
          setLoadingApiKeys(false);
        }
      }
    }

    loadApiKeys();

    return () => {
      cancelled = true;
    };
  }, [agent.agent_id]);

  const handleCreateApiKey = async () => {
    if (!newKeyName.trim()) return;
    setIsCreatingKey(true);
    setCreateKeyError(null);
    try {
      const origins = newKeyOrigins
        .split("\n")
        .map((origin) => origin.trim())
        .filter((origin) => origin.length > 0);

      const newKey = await apiKeyService.createApiKey(agent.agent_id, {
        name: newKeyName.trim(),
        allowed_origins: origins,
        allow_guests: newKeyAllowGuests,
      });

      setApiKeys((prev) => [newKey, ...prev]);
      setIsCreateKeyDialogOpen(false);
      setNewKeyName("");
      setNewKeyOrigins("");
      setNewKeyAllowGuests(false);
      setVisibleKeyId(newKey.key_id);
    } catch (err: unknown) {
      setCreateKeyError(err instanceof Error ? err.message : "Failed to create API key");
    } finally {
      setIsCreatingKey(false);
    }
  };

  const handleDeleteApiKey = async () => {
    if (!deletingKey) return;
    setIsDeletingKey(true);
    try {
      await apiKeyService.deleteApiKey(agent.agent_id, deletingKey);
      setApiKeys((prev) => prev.filter((key) => key.key_id !== deletingKey));
      setDeletingKey(null);
    } catch (err) {
      console.error("Error deleting API key:", err);
    } finally {
      setIsDeletingKey(false);
    }
  };

  const handleIssueA2ASecret = async (key: ApiKeyResponse) => {
    if (key.has_a2a_secret && !window.confirm("Rotate the A2A client secret? A2A callers using the current one will stop working.")) {
      return;
    }
    setIssuingA2AKeyId(key.key_id);
    try {
      const issued = await apiKeyService.issueA2ASecret(agent.agent_id, key.key_id);
      setRevealedA2ASecret({ keyId: key.key_id, secret: issued.client_secret });
      setApiKeys((prev) => prev.map((item) => (item.key_id === key.key_id ? { ...item, has_a2a_secret: true } : item)));
    } catch (err) {
      console.error("Error issuing A2A secret:", err);
    } finally {
      setIssuingA2AKeyId(null);
    }
  };

  const handleGuestToggle = async (key: ApiKeyResponse) => {
    if (updatingGuestKeyId) return;
    setUpdatingGuestKeyId(key.key_id);
    setGuestUpdateError(null);
    try {
      const updated = await apiKeyService.updateApiKey(agent.agent_id, key.key_id, { allow_guests: !key.allow_guests });
      setApiKeys((prev) => prev.map((item) => item.key_id === key.key_id ? updated : item));
    } catch (err) {
      setGuestUpdateError({ keyId: key.key_id, message: err instanceof Error ? err.message : "Couldn't update guest access. Please try again." });
    } finally {
      setUpdatingGuestKeyId(null);
    }
  };

  const handleCopyKey = async (keyId: string, publicKey: string) => {
    try {
      await navigator.clipboard.writeText(publicKey);
      setCopiedKeyId(keyId);
      setTimeout(() => setCopiedKeyId(null), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  return (
    <>
      <div className={styles.page}>
        <Card>
          <CardHeader>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Key style={{ height: "1.25rem", width: "1.25rem", color: "var(--gradient-start)" }} />
                <CardTitle className="text-lg">Widget API Keys</CardTitle>
              </div>
              <Button size="sm" onClick={() => setIsCreateKeyDialogOpen(true)}>
                <Plus style={{ height: "1rem", width: "1rem" }} />
                New Key
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
              API keys allow you to embed this agent as a chat widget on your website.
            </p>
            {loadingApiKeys ? (
              <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
                <div style={{ height: "2rem", width: "2rem", animation: "spin 1s linear infinite", borderRadius: "50%", border: "2px solid var(--gradient-start)", borderTopColor: "transparent" }} />
              </div>
            ) : apiKeys.length === 0 ? (
              <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>
                <Key style={{ height: "3rem", width: "3rem", margin: "0 auto 1rem", opacity: 0.5 }} />
                <p>No API keys yet</p>
                <p style={{ fontSize: "0.875rem" }}>Create an API key to embed this agent on your website</p>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {apiKeys.map((key) => (
                  <div key={key.key_id} style={{ border: "1px solid var(--border-subtle)", borderRadius: "0.5rem", padding: "1rem", backgroundColor: key.is_active ? "transparent" : "rgba(239, 68, 68, 0.05)" }}>
                    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem" }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                          <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{key.name}</span>
                          {!key.is_active && (
                            <span style={{ fontSize: "0.75rem", color: "#f87171", backgroundColor: "rgba(239, 68, 68, 0.1)", padding: "0.125rem 0.5rem", borderRadius: "0.25rem" }}>
                              Disabled
                            </span>
                          )}
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontFamily: "monospace", fontSize: "0.8125rem", backgroundColor: "var(--bg-tertiary)", padding: "0.5rem 0.75rem", borderRadius: "0.375rem", marginBottom: "0.5rem" }}>
                          <code style={{ color: "var(--text-secondary)", flex: 1 }}>
                            {visibleKeyId === key.key_id ? key.public_key : `${key.public_key.slice(0, 12)}••••••••••••••••`}
                          </code>
                          <Button variant="ghost" size="icon" style={{ height: "1.5rem", width: "1.5rem" }} onClick={() => setVisibleKeyId((prev) => (prev === key.key_id ? null : key.key_id))}>
                            {visibleKeyId === key.key_id ? <EyeOff style={{ height: "0.875rem", width: "0.875rem" }} /> : <Eye style={{ height: "0.875rem", width: "0.875rem" }} />}
                          </Button>
                          <Button variant="ghost" size="icon" style={{ height: "1.5rem", width: "1.5rem" }} onClick={() => handleCopyKey(key.key_id, key.public_key)}>
                            {copiedKeyId === key.key_id ? <Check style={{ height: "0.875rem", width: "0.875rem", color: "#10b981" }} /> : <Copy style={{ height: "0.875rem", width: "0.875rem" }} />}
                          </Button>
                        </div>

                        {key.allowed_origins.length > 0 ? (
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                            <Globe style={{ height: "0.75rem", width: "0.75rem", color: "var(--text-muted)" }} />
                            {key.allowed_origins.map((origin, index) => (
                              <span key={index} style={{ fontSize: "0.75rem", color: "var(--text-muted)", backgroundColor: "var(--bg-tertiary)", padding: "0.125rem 0.5rem", borderRadius: "0.25rem" }}>
                                {origin}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <Globe style={{ height: "0.75rem", width: "0.75rem", color: "var(--text-muted)" }} />
                            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>All origins allowed</span>
                          </div>
                        )}

                        <div style={{ display: "flex", gap: "1rem", marginTop: "0.5rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                          <span>{key.request_count.toLocaleString()} requests</span>
                          {key.last_used_at && <span>Last used: {new Date(key.last_used_at).toLocaleDateString()}</span>}
                          <span>Created: {new Date(key.created_at).toLocaleDateString()}</span>
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.5rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                          <span>A2A client secret: {key.has_a2a_secret ? "set" : "none"}</span>
                          <Button variant="ghost" size="sm" disabled={issuingA2AKeyId === key.key_id} onClick={() => void handleIssueA2ASecret(key)}>
                            {key.has_a2a_secret ? "Rotate" : "Generate"}
                          </Button>
                        </div>
                        <div style={{ marginTop: "0.5rem", fontSize: "0.75rem" }}>
                          <label>
                            <input type="checkbox" checked={key.allow_guests === true} disabled={updatingGuestKeyId !== null}
                              aria-describedby={`guest-help-${key.key_id}`} onChange={() => void handleGuestToggle(key)} />
                            {" "}Allow guest visitors
                          </label>
                          <p id={`guest-help-${key.key_id}`} style={{ color: "var(--text-muted)" }}>{guestHelp}</p>
                          {updatingGuestKeyId === key.key_id && <p role="status">Saving guest access…</p>}
                          {guestUpdateError?.keyId === key.key_id && <p role="alert">{guestUpdateError.message}</p>}
                        </div>
                        {revealedA2ASecret?.keyId === key.key_id && (
                          <div style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            <p style={{ marginBottom: "0.25rem" }}>
                              Copy it now: it won't be shown again. Use it as the A2A Bearer token, or as the OAuth client secret with client id <code>{key.key_id}</code>.
                            </p>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontFamily: "monospace", fontSize: "0.8125rem", backgroundColor: "var(--bg-tertiary)", padding: "0.5rem 0.75rem", borderRadius: "0.375rem" }}>
                              <code style={{ color: "var(--text-secondary)", flex: 1, wordBreak: "break-all" }}>{revealedA2ASecret.secret}</code>
                              <Button variant="ghost" size="icon" style={{ height: "1.5rem", width: "1.5rem" }} onClick={() => handleCopyKey(`a2a:${key.key_id}`, revealedA2ASecret.secret)}>
                                {copiedKeyId === `a2a:${key.key_id}` ? <Check style={{ height: "0.875rem", width: "0.875rem", color: "#10b981" }} /> : <Copy style={{ height: "0.875rem", width: "0.875rem" }} />}
                              </Button>
                            </div>
                          </div>
                        )}
                      </div>
                      <Button variant="ghost" size="icon" style={{ color: "#f87171", height: "2rem", width: "2rem" }} onClick={() => setDeletingKey(key.key_id)}>
                        <Trash2 style={{ height: "0.875rem", width: "0.875rem" }} />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {apiKeys.length > 0 && <WidgetSnippets publicKey={apiKeys[0].public_key} />}
          </CardContent>
        </Card>

        <SecretKeysCard agentId={agent.agent_id} />
      </div>

      <Dialog open={isCreateKeyDialogOpen} onOpenChange={setIsCreateKeyDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create API Key</DialogTitle>
            <DialogDescription>
              Create a new API key to embed this agent as a chat widget on your website.
            </DialogDescription>
          </DialogHeader>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {createKeyError && (
              <div style={{ padding: "0.75rem", borderRadius: "0.5rem", backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.2)", color: "#f87171", fontSize: "0.875rem" }}>
                {createKeyError}
              </div>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="key-name">Key Name *</Label>
              <Input id="key-name" placeholder="e.g., Production Website, Development" value={newKeyName} onChange={(e) => setNewKeyName(e.target.value)} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <Label htmlFor="key-origins">Allowed Origins (optional)</Label>
              <Textarea id="key-origins" placeholder={"https://example.com\nhttps://www.example.com"} value={newKeyOrigins} onChange={(e) => setNewKeyOrigins(e.target.value)} rows={3} />
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                One URL per line. Leave empty to allow all origins.
              </p>
            </div>
            <div>
              <label><input type="checkbox" checked={newKeyAllowGuests} disabled={isCreatingKey}
                aria-describedby="new-key-guest-help" onChange={(event) => setNewKeyAllowGuests(event.target.checked)} /> Allow guest visitors</label>
              <p id="new-key-guest-help" style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{guestHelp}</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateKeyDialogOpen(false)} disabled={isCreatingKey}>Cancel</Button>
            <Button onClick={handleCreateApiKey} disabled={!newKeyName.trim() || isCreatingKey}>
              {isCreatingKey ? "Creating..." : "Create Key"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deletingKey} onOpenChange={() => setDeletingKey(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete API Key</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this API key? Any websites using this key will no longer be able to access the widget.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingKey(null)} disabled={isDeletingKey}>Cancel</Button>
            <Button variant="destructive" onClick={handleDeleteApiKey} disabled={isDeletingKey}>
              {isDeletingKey ? "Deleting..." : "Delete Key"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
