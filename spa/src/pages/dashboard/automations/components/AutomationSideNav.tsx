import { BarChart3, History, Timer, Workflow } from "lucide-react";
import { NavLink, useLocation, useParams } from "react-router-dom";

import { cn } from "../../../../lib/utils";

const navItems = [
  { path: "", label: "Builder", icon: Workflow, end: true },
  { path: "triggers", label: "Triggers", icon: Timer },
  { path: "runs", label: "Runs", icon: History },
  { path: "analytics", label: "Analytics", icon: BarChart3 },
];

export function AutomationSideNav() {
  const { automationId } = useParams<{ automationId: string }>();
  const location = useLocation();

  if (!automationId) return null;

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
            ? `/dashboard/automations/${automationId}/${item.path}`
            : `/dashboard/automations/${automationId}`;
          const isActive = item.end ? location.pathname === to : location.pathname.startsWith(to);

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
