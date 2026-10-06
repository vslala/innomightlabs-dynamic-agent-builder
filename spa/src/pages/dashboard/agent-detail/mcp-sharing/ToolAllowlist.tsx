import { useState } from "react";
import { RefreshCw } from "lucide-react";

import { Button, Checkbox, SearchInput } from "../../../../components/ui";
import { cn } from "../../../../lib/utils";
import type { MCPToolCatalog } from "../../../../types/connectors";
import { formatRelativeTime } from "../../../../utils/time";
import { groupTools, toggled, type ToolRisk } from "./sharingDraft";
import styles from "./MCPSharingDialog.module.css";

const RISKS: Record<ToolRisk, { title: string; hint: string }> = {
  read: { title: "Read-only", hint: "Looks things up without changing anything." },
  write: { title: "Can change data", hint: "Creates or updates things in your account." },
  destructive: { title: "Destructive", hint: "May delete or overwrite things. Shared only if you pick it." },
};

interface ToolAllowlistProps {
  catalog: MCPToolCatalog;
  selected: string[];
  onChange: (tools: string[]) => void;
  onRefresh: () => Promise<void>;
}

export function ToolAllowlist({ catalog, selected, onChange, onRefresh }: ToolAllowlistProps) {
  const [query, setQuery] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const groups = groupTools(catalog.tools, query);

  const refresh = async () => {
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className={styles.allowlist}>
      <div className={styles.allowlistBar}>
        <span className={styles.count}>
          <strong>{selected.length}</strong> of {catalog.tools.length} tools shared
        </span>
        <span className={styles.refreshed}>
          Listed {formatRelativeTime(catalog.fetched_at)}
          <Button variant="ghost" size="sm" onClick={() => void refresh()} disabled={refreshing}>
            <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
            Refresh
          </Button>
        </span>
      </div>

      {catalog.tools.length > 6 && (
        <SearchInput placeholder="Search tools" value={query} onChange={(event) => setQuery(event.target.value)} />
      )}

      {groups.length === 0 && (
        <p className={styles.quiet}>{query ? "No tools match your search." : "This connector offers no tools."}</p>
      )}

      {groups.map(({ risk, tools }) => {
        const names = tools.map((tool) => tool.name);
        const allSelected = names.every((name) => selected.includes(name));
        return (
          <section key={risk} className={styles.group} data-risk={risk}>
            <header className={styles.groupHeader}>
              <span className={styles.riskDot} />
              <span className={styles.groupTitle}>{RISKS[risk].title}</span>
              <span className={styles.groupHint}>{RISKS[risk].hint}</span>
              <button
                type="button"
                className={styles.groupAction}
                onClick={() =>
                  onChange(
                    allSelected
                      ? selected.filter((name) => !names.includes(name))
                      : [...new Set([...selected, ...names])]
                  )
                }
              >
                {allSelected ? "Clear" : "Select all"}
              </button>
            </header>
            <ul className={styles.tools}>
              {tools.map((tool) => (
                <li key={tool.name}>
                  <label className={styles.tool}>
                    <Checkbox
                      checked={selected.includes(tool.name)}
                      onChange={() => onChange(toggled(selected, tool.name))}
                    />
                    <span className={styles.toolText}>
                      <span className={styles.toolName}>
                        {tool.title && <span>{tool.title}</span>}
                        <code>{tool.name}</code>
                      </span>
                      {tool.description && <span className={styles.toolDescription}>{tool.description}</span>}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
