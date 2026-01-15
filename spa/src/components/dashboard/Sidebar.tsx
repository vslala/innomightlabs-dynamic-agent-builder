import { NavLink, useLocation } from "react-router-dom";
import { Bot, MessageSquare, Settings, LogOut, Home } from "lucide-react";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { authService } from "../../services/auth";

const navItems = [
  { to: "/dashboard", icon: Home, label: "Overview" },
  { to: "/dashboard/agents", icon: Bot, label: "Agents" },
  { to: "/dashboard/conversations", icon: MessageSquare, label: "Conversations" },
  { to: "/dashboard/settings", icon: Settings, label: "Settings" },
];

export function Sidebar() {
  const location = useLocation();

  const handleLogout = () => {
    authService.logout();
  };

  return (
    <aside className="w-64 min-w-64 h-screen border-r border-[var(--border-subtle)] bg-[#0a0a1a]">
      <div className="flex h-full flex-col">
        {/* Logo */}
        <div className="h-16 flex items-center px-4 border-b border-[var(--border-subtle)]">
          <span className="text-base font-bold gradient-text">InnoMight Labs</span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map((item) => {
            const isActive =
              item.to === "/dashboard"
                ? location.pathname === "/dashboard"
                : location.pathname.startsWith(item.to);

            return (
              <NavLink key={item.to} to={item.to}>
                <div
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200",
                    isActive
                      ? "bg-gradient-to-r from-[var(--gradient-start)]/15 to-[var(--gradient-mid)]/15 text-white"
                      : "text-[var(--text-muted)] hover:bg-white/5 hover:text-[var(--text-primary)]"
                  )}
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {item.label}
                </div>
              </NavLink>
            );
          })}
        </nav>

        {/* Logout */}
        <div className="p-3 border-t border-[var(--border-subtle)]">
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start gap-3 h-9 px-3 text-sm text-[var(--text-muted)] hover:text-red-400 hover:bg-red-500/10"
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
