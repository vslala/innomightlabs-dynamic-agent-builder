import type { ReactNode } from "react";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../../../components/ui";
import type { MCPConnection, MCPProvider } from "../../../types/connectors";
import { ConnectorIcon } from "./ConnectorIcon";
import styles from "./ConnectorCatalog.module.css";
import { MCPConnectionCard } from "./MCPConnectionCard";

interface ConnectorDetailsDialogProps {
  title: string;
  description: string;
  icon: string;
  connections: MCPConnection[];
  providerFor: (connection: MCPConnection) => MCPProvider | null;
  canManage: boolean;
  signingInId: string | null;
  deletingId: string | null;
  runtimeVersion: number;
  onSignIn: (connection: MCPConnection) => void;
  onEdit: (connection: MCPConnection) => void;
  onDelete: (connection: MCPConnection) => void;
  onClose: () => void;
  /** Extra actions under the connections, e.g. "Add another" or a Google reconnect. */
  footer?: ReactNode;
}

/** What one connector has installed on the account, with the actions for each install. */
export function ConnectorDetailsDialog({
  title,
  description,
  icon,
  connections,
  providerFor,
  canManage,
  signingInId,
  deletingId,
  runtimeVersion,
  onSignIn,
  onEdit,
  onDelete,
  onClose,
  footer,
}: ConnectorDetailsDialogProps) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent style={{ maxWidth: "40rem" }}>
        <DialogHeader>
          <DialogTitle style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <ConnectorIcon icon={icon} name={title} size="sm" />
            {title}
          </DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {connections.length > 0 && (
          <div className={styles.detailsList}>
            {connections.map((connection) => (
              <MCPConnectionCard
                key={`${connection.mcp_id}-${runtimeVersion}`}
                connection={connection}
                provider={providerFor(connection)}
                canManage={canManage}
                signingIn={signingInId === connection.mcp_id}
                deleting={deletingId === connection.mcp_id}
                onSignIn={() => onSignIn(connection)}
                onEdit={() => onEdit(connection)}
                onDelete={() => onDelete(connection)}
              />
            ))}
          </div>
        )}
        {footer}
      </DialogContent>
    </Dialog>
  );
}
