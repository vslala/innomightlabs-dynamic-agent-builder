import { useMemo, useState } from "react";
import { MoreHorizontal, Plus, Server } from "lucide-react";

import { Button, SearchInput } from "../../../components/ui";
import type { MCPConnection } from "../../../types/connectors";
import { buildCatalogSections, customConnections, filterCatalog, type CatalogItem } from "./catalogItems";
import { ConnectorIcon } from "./ConnectorIcon";
import { connectionIcon } from "./connectionIcon";
import styles from "./ConnectorCatalog.module.css";

interface ConnectorCatalogProps {
  items: CatalogItem[];
  connections: MCPConnection[];
  canManage: boolean;
  busyKey: string | null;
  onInstall: (item: CatalogItem) => void;
  onManage: (item: CatalogItem) => void;
  onManageCustom: (connection: MCPConnection) => void;
  onAddCustom: () => void;
}

/** Search, the installed strip, then rows by category. Install and manage open dialogs on the page. */
export function ConnectorCatalog({
  items,
  connections,
  canManage,
  busyKey,
  onInstall,
  onManage,
  onManageCustom,
  onAddCustom,
}: ConnectorCatalogProps) {
  const [query, setQuery] = useState("");
  const searching = query.trim() !== "";
  const matches = useMemo(() => filterCatalog(items, query), [items, query]);
  const sections = useMemo(() => buildCatalogSections(matches, searching), [matches, searching]);
  const custom = useMemo(() => customConnections(connections), [connections]);
  const installed = items.filter((item) => item.installed);

  return (
    <div className={styles.catalog}>
      <SearchInput
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search connectors"
        aria-label="Search connectors"
      />

      {!searching && (installed.length > 0 || custom.length > 0) && (
        <section aria-label="Installed connectors">
          <h2 className={styles.sectionTitle}>Installed</h2>
          <div className={styles.strip}>
            {installed.map((item) => (
              <Button
                key={item.key}
                type="button"
                variant="ghost"
                className={styles.chip}
                onClick={() => onManage(item)}
                aria-label={`${item.name}${item.needsAttention ? ", needs attention" : ""}`}
                title={item.name}
              >
                <ConnectorIcon icon={item.icon} name={item.name} />
                {item.needsAttention && <span className={styles.attentionDot} />}
              </Button>
            ))}
            {custom.map((connection) => (
              <Button
                key={connection.mcp_id}
                type="button"
                variant="ghost"
                className={styles.chip}
                onClick={() => onManageCustom(connection)}
                aria-label={connection.name}
                title={connection.name}
              >
                <ConnectorIcon icon={connectionIcon(connection)} name={connection.name} />
                {connection.auth_type === "oauth" && !connection.oauth_connected && <span className={styles.attentionDot} />}
              </Button>
            ))}
          </div>
        </section>
      )}

      {sections.map((section) => (
        <section key={section.id} aria-label={section.title}>
          <h2 className={styles.sectionTitle}>{section.title}</h2>
          <div className={styles.rows}>
            {section.items.map((item) => (
              <div key={item.key} className={styles.row}>
                <ConnectorIcon icon={item.icon} name={item.name} />
                <div className={styles.rowText}>
                  <div className={styles.rowName}>{item.name}</div>
                  <div className={styles.rowDescription} title={item.description}>
                    {item.description}
                  </div>
                </div>
                <div className={styles.rowAction}>
                  {item.installed ? (
                    <Button variant="ghost" size="sm" onClick={() => onManage(item)} aria-label={`Manage ${item.name}`}>
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  ) : (
                    canManage && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onInstall(item)}
                        disabled={busyKey === item.key}
                        aria-label={`Install ${item.name}`}
                      >
                        <Plus className="h-4 w-4" />
                      </Button>
                    )
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}

      {searching && sections.length === 0 && (
        <p className={styles.empty}>
          No connectors match "{query.trim()}".{canManage && " You can add your own server below."}
        </p>
      )}

      {(canManage || custom.length > 0) && (
        <section aria-label="Your own server">
          <h2 className={styles.sectionTitle}>Your own server</h2>
          <div className={styles.rows}>
            {custom.map((connection) => (
              <div key={connection.mcp_id} className={styles.row}>
                <ConnectorIcon icon={connectionIcon(connection)} name={connection.name} />
                <div className={styles.rowText}>
                  <div className={styles.rowName}>{connection.name}</div>
                  <div className={styles.rowDescription} title={connection.server_url}>
                    {connection.server_url}
                  </div>
                </div>
                <div className={styles.rowAction}>
                  <Button variant="ghost" size="sm" onClick={() => onManageCustom(connection)} aria-label={`Manage ${connection.name}`}>
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
            {canManage && (
              <div className={styles.row}>
                <span className={styles.tile}>
                  <Server className={styles.tileGlyph} aria-hidden="true" />
                </span>
                <div className={styles.rowText}>
                  <div className={styles.rowName}>Add your own</div>
                  <div className={styles.rowDescription}>Connect any remote or hosted MCP server.</div>
                </div>
                <div className={styles.rowAction}>
                  <Button variant="ghost" size="sm" onClick={onAddCustom} aria-label="Add custom MCP server">
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
