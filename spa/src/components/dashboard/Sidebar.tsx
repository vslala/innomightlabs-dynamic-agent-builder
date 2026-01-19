import { NavLink, useLocation } from "react-router-dom";
import { Bot, MessageSquare, Settings, LogOut, Home, Database } from "lucide-react";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { authService } from "../../services/auth";

const navItems = [
  { to: "/dashboard", icon: Home, label: "Overview" },
  { to: "/dashboard/agents", icon: Bot, label: "Agents" },
  { to: "/dashboard/conversations", icon: MessageSquare, label: "Conversations" },
  { to: "/dashboard/knowledge-bases", icon: Database, label: "Knowledge Bases" },
  { to: "/dashboard/settings", icon: Settings, label: "Settings" },
];

export function Sidebar() {
  const location = useLocation();

  const handleLogout = () => {
    authService.logout();
  };

  return (
    <aside
      style={{
        width: "16rem",
        minWidth: "16rem",
        borderRight: "1px solid var(--border-subtle)",
        backgroundColor: "#0a0a1a",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100vh",
          position: "sticky",
          top: 0,
        }}
      >
        {/* Logo */}
        <div
          style={{
            height: "4rem",
            display: "flex",
            alignItems: "center",
            padding: "0 1rem",
            borderBottom: "1px solid var(--border-subtle)",
          }}
        >
          <span className="gradient-text" style={{ fontSize: "1rem", fontWeight: 700 }}>InnoMight Labs</span>
        </div>

        {/* Navigation */}
        <nav style={{ flex: 1, padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          {navItems.map((item) => {
            const isActive =
              item.to === "/dashboard"
                ? location.pathname === "/dashboard"
                : location.pathname.startsWith(item.to);

            return (
              <NavLink key={item.to} to={item.to}>
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
                    borderRadius: "0.5rem",
                    padding: "0.625rem 0.75rem",
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

        {/* Logout */}
        <div style={{ padding: "0.75rem", borderTop: "1px solid var(--border-subtle)" }}>
          <Button
            variant="ghost"
            size="sm"
            className="hover:text-red-400 hover:bg-red-500/10"
            style={{
              width: "100%",
              justifyContent: "flex-start",
              gap: "0.75rem",
              height: "2.25rem",
              padding: "0 0.75rem",
              fontSize: "0.875rem",
              color: "var(--text-muted)",
            }}
            onClick={handleLogout}
          >
            <LogOut className="h-4 w-4 shrink-0" />
            Logout
          </Button>
        </div>
      </div>
    </aside>
  );
}
