import { NavLink, useLocation, useParams } from "react-router-dom";
import { BarChart3, BookOpen, Bot, Database, Key, Network, Server, Wrench } from "lucide-react";

import { cn } from "../../../lib/utils";
import "./AgentSideNav.css";

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
  { path: "a2a-tasks", label: "A2A Tasks", icon: Network },
  { path: "analytics", label: "Analytics", icon: BarChart3 },
];

export function AgentSideNav() {
  const { agentId } = useParams<{ agentId: string }>();
  const location = useLocation();

  if (!agentId) return null;

  return (
    <aside className="agent-side-nav">
      <nav className="agent-side-nav__list">
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
                  "agent-side-nav__item",
                  isActive ? "agent-side-nav__item--active" : "agent-side-nav__item--idle"
                )}
              >
                <item.icon className="agent-side-nav__icon" />
                {item.label}
              </div>
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}
