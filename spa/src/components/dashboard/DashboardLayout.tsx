import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { OAuthReturn } from "./OAuthReturn";
import { AgentQuickSwitcher } from "./AgentQuickSwitcher";
import { cn } from "../../lib/utils";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { authService, type UserInfo } from "../../services/auth";
import "./DashboardLayout.css";

const pageTitles: Record<string, string> = {
  "/dashboard": "Overview",
  "/dashboard/agents": "Agents",
  "/dashboard/automations": "Automations",
  "/dashboard/conversations": "Conversations",
  "/dashboard/artifacts": "Artifacts",
  "/dashboard/knowledge-bases": "Knowledge Bases",
  "/dashboard/connectors": "Connectors",
  "/dashboard/iam": "IAM",
  "/dashboard/iam/members": "IAM — Members",
  "/dashboard/whats-new": "What's New",
  "/dashboard/settings": "Settings",
};

/** Below this width the sidebar is a drawer. Keep in step with the 900px rules in Sidebar.css and Header.css. */
const COMPACT_QUERY = "(max-width: 900px)";
const NAVIGATION_ID = "dashboard-navigation";

const AUTOMATION_WORKSPACE_PATTERN = /^\/dashboard\/automations\/(?!marketplace)[^/]+(\/(triggers|runs|analytics))?$/;

function isAutomationWorkspace(pathname: string): boolean {
  return AUTOMATION_WORKSPACE_PATTERN.test(pathname);
}

export function DashboardLayout() {
  const location = useLocation();
  // The automation workspace and the conversation view draw their own chrome
  // edge to edge, so the dashboard drops its content padding for them.
  const isFullBleedPage =
    location.pathname === "/dashboard/conversations" || isAutomationWorkspace(location.pathname);
  const isSettingsPage = location.pathname === "/dashboard/settings";

  const compact = useMediaQuery(COMPACT_QUERY);
  // The path the drawer was opened on: going anywhere else closes it without an effect to do so
  const [drawerPath, setDrawerPath] = useState<string | null>(null);
  if (!compact && drawerPath !== null) {
    // Widened to where the sidebar is always shown; narrowing again must not bring the drawer back
    setDrawerPath(null);
  }
  const drawerOpen = compact && drawerPath === location.pathname;
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const sidebar = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!drawerOpen) {
      return;
    }
    sidebar.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDrawerPath(null);
        menuButton.current?.focus();
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [drawerOpen]);

  useEffect(() => {
    const openOnShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSwitcherOpen(true);
      }
    };
    document.addEventListener("keydown", openOnShortcut);
    return () => document.removeEventListener("keydown", openOnShortcut);
  }, []);

  const closeDrawer = () => {
    setDrawerPath(null);
    menuButton.current?.focus();
  };

  useEffect(() => {
    if (!isSettingsPage) {
      return;
    }

    const previousBodyOverflow = document.body.style.overflow;
    const previousHtmlOverscrollBehavior = document.documentElement.style.overscrollBehaviorY;

    document.body.style.overflow = "hidden";
    document.documentElement.style.overscrollBehaviorY = "none";

    return () => {
      document.body.style.overflow = previousBodyOverflow;
      document.documentElement.style.overscrollBehaviorY = previousHtmlOverscrollBehavior;
    };
  }, [isSettingsPage]);

  // Get user from token - ProtectedRoute ensures we have a valid token
  const user: UserInfo | null = authService.getUserFromToken();

  // Get title based on current path
  const getTitle = () => {
    // Exact match first
    if (pageTitles[location.pathname]) {
      return pageTitles[location.pathname];
    }
    // Check for agent detail page
    if (location.pathname.startsWith("/dashboard/agents/")) {
      if (location.pathname.endsWith("/memory")) {
        return "Agent Memory";
      }
      if (location.pathname.endsWith("/api-keys")) {
        return "Agent API Keys";
      }
      if (location.pathname.endsWith("/knowledge-bases")) {
        return "Agent Knowledge Bases";
      }
      if (location.pathname.endsWith("/skills")) {
        return "Agent Skills";
      }
      if (location.pathname.endsWith("/analytics")) {
        return "Agent Analytics";
      }
      return "Agent Overview";
    }
    if (location.pathname.startsWith("/dashboard/automations/")) {
      if (location.pathname.endsWith("/runs")) {
        return "Automation Runs";
      }
      if (location.pathname.endsWith("/analytics")) {
        return "Automation Analytics";
      }
      return "Automation Builder";
    }
    if (location.pathname.startsWith("/dashboard/artifacts/")) {
      return "Artifact";
    }
    // Check for knowledge base detail page
    if (location.pathname.startsWith("/dashboard/knowledge-bases/")) {
      return "Knowledge Base";
    }
    return "Dashboard";
  };

  return (
    <div className="dashboard-layout">
      <Sidebar ref={sidebar} id={NAVIGATION_ID} open={drawerOpen} compact={compact} onClose={closeDrawer} />
      {drawerOpen && (
        // Escape and the drawer's own close button are the keyboard routes; this is the tap-outside one
        <div className="dashboard-layout__backdrop" aria-hidden="true" onClick={closeDrawer} />
      )}
      {/* While the drawer is open, nothing behind it can be reached by keyboard or screen reader */}
      <div className="dashboard-layout__body" inert={drawerOpen}>
        <Header
          ref={menuButton}
          title={getTitle()}
          user={user || undefined}
          navigationId={NAVIGATION_ID}
          navigationOpen={drawerOpen}
          onMenuClick={() => setDrawerPath(location.pathname)}
          onSwitcherClick={() => setSwitcherOpen(true)}
        />
        <main
          className={cn(
            "dashboard-layout__main",
            isFullBleedPage && "dashboard-layout__main--full-bleed",
            isSettingsPage && "dashboard-layout__main--settings"
          )}
        >
          <div className="dashboard-layout__content">
            <OAuthReturn>
              <Outlet context={{ user }} />
            </OAuthReturn>
          </div>
        </main>
      </div>
      <AgentQuickSwitcher open={switcherOpen} onOpenChange={setSwitcherOpen} />
    </div>
  );
}
