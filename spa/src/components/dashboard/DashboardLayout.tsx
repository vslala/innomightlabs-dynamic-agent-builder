import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { authService, type UserInfo } from "../../services/auth";

const pageTitles: Record<string, string> = {
  "/dashboard": "Overview",
  "/dashboard/agents": "Agents",
  "/dashboard/automations": "Automations",
  "/dashboard/conversations": "Conversations",
  "/dashboard/knowledge-bases": "Knowledge Bases",
  "/dashboard/connectors": "Connectors",
  "/dashboard/whats-new": "What's New",
  "/dashboard/settings": "Settings",
};

export function DashboardLayout() {
  const location = useLocation();

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
    // Check for knowledge base detail page
    if (location.pathname.startsWith("/dashboard/knowledge-bases/")) {
      return "Knowledge Base";
    }
    return "Dashboard";
  };

  return (
    <div
      style={{
        display: "flex",
        minHeight: "100vh",
        backgroundColor: "var(--bg-dark)",
      }}
    >
      <Sidebar />
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minHeight: "100vh",
        }}
      >
        <Header title={getTitle()} user={user || undefined} />
        <main
          style={{
            flex: 1,
            padding: "2rem",
            overflowY: "auto",
          }}
        >
          <div style={{ maxWidth: "80rem", margin: "0 auto" }}>
            <Outlet context={{ user }} />
          </div>
        </main>
      </div>
    </div>
  );
}
