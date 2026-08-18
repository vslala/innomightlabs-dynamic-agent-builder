import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { cn } from "../../lib/utils";
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
  "/dashboard/whats-new": "What's New",
  "/dashboard/settings": "Settings",
};

export function DashboardLayout() {
  const location = useLocation();
  const isFullBleedPage = location.pathname === "/dashboard/conversations";

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
      <Sidebar />
      <div className="dashboard-layout__body">
        <Header title={getTitle()} user={user || undefined} />
        <main
          className={cn(
            "dashboard-layout__main",
            isFullBleedPage && "dashboard-layout__main--full-bleed"
          )}
        >
          <div className="dashboard-layout__content">
            <Outlet context={{ user }} />
          </div>
        </main>
      </div>
    </div>
  );
}
