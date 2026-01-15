import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { authService, type UserInfo } from "../../services/auth";

const pageTitles: Record<string, string> = {
  "/dashboard": "Overview",
  "/dashboard/agents": "Agents",
  "/dashboard/conversations": "Conversations",
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
      return "Agent Details";
    }
    return "Dashboard";
  };

  return (
    <div className="flex min-h-screen bg-[var(--bg-dark)]">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header title={getTitle()} user={user || undefined} />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet context={{ user }} />
        </main>
      </div>
    </div>
  );
}
