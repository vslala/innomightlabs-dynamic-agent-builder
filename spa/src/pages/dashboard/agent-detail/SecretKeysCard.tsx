import { useEffect, useState } from "react";
import { Check, Copy, KeyRound, Plus, Trash2 } from "lucide-react";

import { AlertBanner } from "../../../components/ui/alert";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { ConfirmationDialog } from "../../../components/ui/confirmation-dialog";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../../../components/ui/dialog";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { LoadingState } from "../../../components/ui/spinner";
import { StatusBadge } from "../../../components/ui/status-badge";
import { secretKeyService, type SecretKeyResponse } from "../../../services/apikeys";
import styles from "./SecretKeysCard.module.css";

interface SecretKeysCardProps {
  agentId: string;
}

export function SecretKeysCard({ agentId }: SecretKeysCardProps) {
  const [keys, setKeys] = useState<SecretKeyResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [revealedSecret, setRevealedSecret] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [updatingKeyId, setUpdatingKeyId] = useState<string | null>(null);
  const [deletingKeyId, setDeletingKeyId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadKeys() {
      setLoading(true);
      try {
        const loaded = await secretKeyService.listSecretKeys(agentId);
        if (!cancelled) setKeys(loaded);
      } catch (err) {
        console.error("Error loading secret keys:", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadKeys();

    return () => {
      cancelled = true;
    };
  }, [agentId]);

  const closeCreateDialog = () => {
    setIsCreateOpen(false);
    setNewKeyName("");
    setCreateError(null);
    setRevealedSecret(null);
    setCopied(false);
  };

  const handleCreate = async () => {
    if (!newKeyName.trim()) return;
    setIsCreating(true);
    setCreateError(null);
    try {
      const { secret, ...created } = await secretKeyService.createSecretKey(agentId, { name: newKeyName.trim() });
      setKeys((prev) => [created, ...prev]);
      setRevealedSecret(secret);
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : "Failed to create API key");
    } finally {
      setIsCreating(false);
    }
  };

  const handleCopySecret = async () => {
    if (!revealedSecret) return;
    try {
      await navigator.clipboard.writeText(revealedSecret);
      setCopied(true);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  const handleToggleActive = async (key: SecretKeyResponse) => {
    setUpdatingKeyId(key.key_id);
    setActionError(null);
    try {
      const updated = await secretKeyService.updateSecretKey(agentId, key.key_id, { is_active: !key.is_active });
      setKeys((prev) => prev.map((existing) => (existing.key_id === updated.key_id ? updated : existing)));
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to update API key");
    } finally {
      setUpdatingKeyId(null);
    }
  };

  const handleDelete = async () => {
    if (!deletingKeyId) return;
    setIsDeleting(true);
    setActionError(null);
    try {
      await secretKeyService.deleteSecretKey(agentId, deletingKeyId);
      setKeys((prev) => prev.filter((key) => key.key_id !== deletingKeyId));
      setDeletingKeyId(null);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to delete API key");
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <>
      <Card>
        <CardHeader>
          <div className={styles.headerRow}>
            <div className={styles.titleGroup}>
              <KeyRound className={styles.titleIcon} />
              <CardTitle className={styles.title}>Server API Keys</CardTitle>
            </div>
            <Button size="sm" onClick={() => setIsCreateOpen(true)}>
              <Plus className={styles.buttonIcon} />
              New Key
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <p className={styles.description}>
            Secret keys let your server chat with this agent through the public API, acting as you.
            Keep them on your server. Never put them in browser code or a public repository.
          </p>

          {actionError && (
            <AlertBanner className={styles.banner} message={actionError} onDismiss={() => setActionError(null)} />
          )}

          {loading ? (
            <LoadingState />
          ) : keys.length === 0 ? (
            <div className={styles.emptyState}>
              <KeyRound className={styles.emptyIcon} />
              <p>No API keys yet</p>
              <p className={styles.emptyHint}>Create a key to call this agent from your server</p>
            </div>
          ) : (
            <ul className={styles.keyList}>
              {keys.map((key) => (
                <li key={key.key_id} className={key.is_active ? styles.keyRow : `${styles.keyRow} ${styles.keyRowDisabled}`}>
                  <div className={styles.keyMain}>
                    <div className={styles.keyTitleRow}>
                      <span className={styles.keyName}>{key.name}</span>
                      <StatusBadge size="sm" status={key.is_active ? "active" : "inactive"} label={key.is_active ? "Active" : "Disabled"} />
                    </div>
                    <code className={styles.keyHint} title="The full key is only shown when it is created">
                      {key.key_hint}
                    </code>
                    <div className={styles.keyMeta}>
                      <span>{key.request_count.toLocaleString()} requests</span>
                      {key.last_used_at && <span>Last used: {new Date(key.last_used_at).toLocaleDateString()}</span>}
                      <span>Created: {new Date(key.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                  <div className={styles.keyActions}>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleToggleActive(key)}
                      disabled={updatingKeyId === key.key_id}
                    >
                      {key.is_active ? "Disable" : "Enable"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className={styles.deleteButton}
                      aria-label={`Delete API key ${key.name}`}
                      onClick={() => setDeletingKeyId(key.key_id)}
                    >
                      <Trash2 className={styles.buttonIcon} />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Dialog open={isCreateOpen} onOpenChange={(open) => (open ? setIsCreateOpen(true) : closeCreateDialog())}>
        <DialogContent>
          {revealedSecret ? (
            <>
              <DialogHeader>
                <DialogTitle>Copy your API key</DialogTitle>
                <DialogDescription>
                  This is the only time the full key is shown. Store it somewhere safe, such as your server's environment variables.
                </DialogDescription>
              </DialogHeader>
              <div className={styles.secretBox}>
                <code className={styles.secretValue}>{revealedSecret}</code>
                <Button variant="ghost" size="icon" aria-label="Copy API key" onClick={handleCopySecret}>
                  {copied ? <Check className={`${styles.buttonIcon} ${styles.copiedIcon}`} /> : <Copy className={styles.buttonIcon} />}
                </Button>
              </div>
              <DialogFooter>
                <Button onClick={closeCreateDialog}>Done</Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle>Create API Key</DialogTitle>
                <DialogDescription>
                  Create a secret key for calling this agent from your server.
                </DialogDescription>
              </DialogHeader>
              <div className={styles.formFields}>
                {createError && <AlertBanner message={createError} />}
                <div className={styles.field}>
                  <Label htmlFor="secret-key-name">Key Name *</Label>
                  <Input
                    id="secret-key-name"
                    placeholder="e.g., Production server, Staging"
                    value={newKeyName}
                    onChange={(e) => setNewKeyName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={closeCreateDialog} disabled={isCreating}>Cancel</Button>
                <Button onClick={handleCreate} disabled={!newKeyName.trim() || isCreating}>
                  {isCreating ? "Creating..." : "Create Key"}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmationDialog
        open={!!deletingKeyId}
        onOpenChange={(open) => !open && setDeletingKeyId(null)}
        title="Delete API Key"
        description="Are you sure you want to delete this API key? Any server using it will immediately lose access to this agent."
        confirmText="Delete Key"
        onConfirm={handleDelete}
        variant="destructive"
        loading={isDeleting}
        loadingText="Deleting..."
      />
    </>
  );
}
