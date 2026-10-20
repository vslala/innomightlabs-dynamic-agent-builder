import { Edit, KeyRound, Settings2, Trash2 } from "lucide-react";

import { Button, StatusBadge } from "../../../components/ui";
import type { MCPConnection, MCPProvider, MCPSetupState } from "../../../types/connectors";
import styles from "./ConnectorCatalog.module.css";
import { MCPRuntimeStatus } from "./MCPRuntimeStatus";

const SETUP_BADGES: Record<MCPSetupState, { status: "active" | "warning" | "info"; label: string }> = {
  ready: { status: "active", label: "Ready" },
  needs_sign_in: { status: "info", label: "Sign in" },
  needs_input: { status: "warning", label: "Needs setup" },
};

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

interface MCPConnectionCardProps {
  connection: MCPConnection;
  provider: MCPProvider | null;
  canManage: boolean;
  signingIn: boolean;
  deleting: boolean;
  onSignIn: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

/** One installed connection: its state, runtime and the actions on it. Shown in the connector's details dialog. */
export function MCPConnectionCard({
  connection,
  provider,
  canManage,
  signingIn,
  deleting,
  onSignIn,
  onEdit,
  onDelete,
}: MCPConnectionCardProps) {
  const isStdio = connection.transport === "stdio";
  const setup = connection.provider_key ? SETUP_BADGES[connection.setup_state] : null;
  const authLabel = { none: "None", api_key: isStdio ? "Environment" : "API key", oauth: "OAuth" }[connection.auth_type];
  const target =
    isStdio && connection.stdio ? [connection.stdio.package, ...connection.stdio.args].join(" ") : connection.server_url;

  return (
    <div className={styles.card}>
      <div className={styles.cardTop}>
        <span className={styles.cardName}>{connection.name}</span>
        <div className={styles.cardBadges}>
          {setup && <StatusBadge status={setup.status} label={setup.label} />}
          <StatusBadge status={connection.enabled ? "active" : "inactive"} label={connection.enabled ? "Enabled" : "Disabled"} />
        </div>
      </div>
      <div className={styles.facts}>
        {!provider && <span>{target}</span>}
        <span>{isStdio ? "Hosted by InnoMight Labs" : "Remote server"}</span>
        <span>
          Sign-in: {authLabel}
          {connection.auth_type === "oauth" ? (connection.oauth_connected ? ", connected" : ", not connected") : ""}
        </span>
        <span>Added {formatDate(connection.created_at)}</span>
      </div>
      {isStdio && (
        <MCPRuntimeStatus
          mcpId={connection.mcp_id}
          canStart={
            canManage &&
            connection.enabled &&
            connection.setup_state === "ready" &&
            (connection.auth_type !== "oauth" || connection.oauth_connected)
          }
        />
      )}
      {canManage && (
        <div className={styles.actions}>
          {connection.auth_type === "oauth" && (
            <Button variant={connection.oauth_connected ? "outline" : "default"} onClick={onSignIn} disabled={signingIn}>
              <KeyRound className="h-4 w-4" />
              {signingIn ? "Opening..." : connection.oauth_connected ? "Sign in again" : "Sign in"}
            </Button>
          )}
          <Button variant="outline" onClick={onEdit}>
            {connection.provider_key ? <Settings2 className="h-4 w-4" /> : <Edit className="h-4 w-4" />}
            {connection.provider_key ? "Settings" : "Edit"}
          </Button>
          <Button variant="outline" onClick={onDelete} disabled={deleting}>
            <Trash2 className="h-4 w-4" />
            {deleting ? "Deleting..." : connection.provider_key ? "Uninstall" : "Delete"}
          </Button>
        </div>
      )}
    </div>
  );
}
