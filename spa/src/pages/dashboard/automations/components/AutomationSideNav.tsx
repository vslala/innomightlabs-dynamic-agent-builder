import { BarChart3, History, Workflow } from "lucide-react";
import { NavLink, useLocation, useParams } from "react-router-dom";

import { cn } from "../../../../lib/utils";

const navItems = [
  { path: "", label: "Builder", icon: Workflow, end: true },
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
                    ? "bg-gradient-to-r from-[var(--gradient-start)]/15 to-[var(--gradient-mid)]/15 text-white"
                    : "text-[var(--text-muted)] hover:bg-white/5 hover:text-[var(--text-primary)]"
                )}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.75rem",
                  borderRadius: "0.75rem",
                  padding: "0.75rem",
                  fontSize: "0.875rem",
                  fontWeight: 500,
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
