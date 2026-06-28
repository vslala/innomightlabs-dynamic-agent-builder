import { NavLink, useLocation, useParams } from "react-router-dom";
import { BarChart3, BookOpen, Bot, Database, Key, Server, Wrench } from "lucide-react";

import { cn } from "../../../lib/utils";

interface AgentNavItem {
  path: string;
  label: string;
  icon: typeof Bot;
  end?: boolean;
}

const navItems: AgentNavItem[] = [
  { path: "", label: "Overview", icon: Bot, end: true },
  { path: "memory", label: "Memory", icon: Database },
  { path: "api-keys", label: "API Keys", icon: Key },
  { path: "knowledge-bases", label: "Knowledge Bases", icon: BookOpen },
  { path: "skills", label: "Skills", icon: Wrench },
  { path: "mcp-tools", label: "MCP Tools", icon: Server },
  { path: "analytics", label: "Analytics", icon: BarChart3 },
];

export function AgentSideNav() {
  const { agentId } = useParams<{ agentId: string }>();
  const location = useLocation();

  if (!agentId) return null;

  return (
    <aside
      style={{
        width: "15rem",
        minWidth: "15rem",
        borderRight: "1px solid var(--border-subtle)",
        paddingRight: "1rem",
      }}
    >
      <nav style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
        {navItems.map((item) => {
          const to = item.path
            ? `/dashboard/agents/${agentId}/${item.path}`
            : `/dashboard/agents/${agentId}`;
          const isActive = item.end
            ? location.pathname === to
            : location.pathname.startsWith(to);

          return (
            <NavLink key={to} to={to} end={item.end}>
              <div
                className={cn(
                  "transition-all duration-200",
                  isActive
                    ? "text-[var(--nav-active-text)]"
                    : "text-[var(--text-muted)] hover:bg-[var(--nav-hover-bg)] hover:text-[var(--text-primary)]"
                )}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.75rem",
                  borderRadius: "0.75rem",
                  padding: "0.75rem",
                  fontSize: "0.875rem",
                  fontWeight: 500,
                  background: isActive
                    ? "linear-gradient(90deg, rgba(12, 102, 228, 0.14), rgba(12, 102, 228, 0.06))"
                    : undefined,
                }}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                {item.label}
              </div>
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}
