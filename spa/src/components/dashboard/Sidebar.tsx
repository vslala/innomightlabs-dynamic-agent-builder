import { forwardRef } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { Archive, Bot, MessageSquare, Settings, LogOut, Home, Database, Workflow, Plug, Sparkles, Hammer, ShieldCheck, UserPlus, X } from "lucide-react";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { authService } from "../../services/auth";
import logo from "../../assets/brand/innomightlabs-logo.png";
import "./Sidebar.css";

const navItems = [
  { to: "/dashboard", icon: Home, label: "Overview" },
  { to: "/dashboard/build", icon: Hammer, label: "Build with Ila" },
  { to: "/dashboard/agents", icon: Bot, label: "Agents" },
  { to: "/dashboard/automations", icon: Workflow, label: "Automations" },
  { to: "/dashboard/leads", icon: UserPlus, label: "Leads" },
  { to: "/dashboard/conversations", icon: MessageSquare, label: "Conversations" },
  { to: "/dashboard/artifacts", icon: Archive, label: "Artifacts" },
  { to: "/dashboard/knowledge-bases", icon: Database, label: "Knowledge Bases" },
  { to: "/dashboard/connectors", icon: Plug, label: "Connectors" },
  { to: "/dashboard/iam", icon: ShieldCheck, label: "IAM" },
  { to: "/dashboard/whats-new", icon: Sparkles, label: "What's New" },
  { to: "/dashboard/settings", icon: Settings, label: "Settings" },
];

interface SidebarProps {
  id: string;
  /** On a narrow screen the sidebar is a drawer; this is whether it is showing. */
  open: boolean;
  /** Whether the layout is narrow enough to use the drawer. */
  compact: boolean;
  onClose: () => void;
}

export const Sidebar = forwardRef<HTMLElement, SidebarProps>(function Sidebar({ id, open, compact, onClose }, ref) {
  const location = useLocation();

  return (
    <aside
      id={id}
      ref={ref}
      tabIndex={-1}
      aria-label="Primary"
      className={cn("dashboard-sidebar", open && "dashboard-sidebar--open")}
      // A closed drawer is off screen: keep it out of the tab order and away from screen readers
      inert={compact && !open}
    >
      <div className="dashboard-sidebar__inner">
        <div className="dashboard-sidebar__brand">
          <img src={logo} alt="InnoMight Labs logo" className="dashboard-sidebar__logo" />
          <span className="gradient-text dashboard-sidebar__name">InnoMight Labs</span>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="dashboard-sidebar__close"
            style={{ width: "2.75rem", height: "2.75rem" }}
            aria-label="Close navigation"
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </Button>
        </div>

        <nav className="dashboard-sidebar__nav" aria-label="Dashboard">
          {navItems.map((item) => {
            const isActive =
              item.to === "/dashboard"
                ? location.pathname === "/dashboard"
                : location.pathname.startsWith(item.to);

            return (
              <NavLink
                key={item.to}
                to={item.to}
                aria-current={isActive ? "page" : undefined}
                className={cn("dashboard-sidebar__link", isActive && "dashboard-sidebar__link--active")}
              >
                <item.icon aria-hidden="true" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>

        <div className="dashboard-sidebar__footer">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="dashboard-sidebar__logout"
            onClick={() => authService.logout()}
          >
            <LogOut aria-hidden="true" />
            Logout
          </Button>
        </div>
      </div>
    </aside>
  );
});
