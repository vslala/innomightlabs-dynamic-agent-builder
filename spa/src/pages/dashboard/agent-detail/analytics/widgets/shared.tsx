import type { DashboardFiltersChangedDetail } from "../types";

export function WidgetLoadingState() {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", minHeight: "8rem" }}>
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--gradient-start)] border-t-transparent" />
    </div>
  );
}

export function WidgetErrorState({ message }: { message: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", minHeight: "8rem", color: "#f87171", textAlign: "center" }}>
      <p style={{ fontSize: "0.875rem" }}>{message}</p>
    </div>
  );
}

export function WidgetEmptyState({ message }: { message: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", minHeight: "8rem", color: "var(--text-muted)", textAlign: "center" }}>
      <p style={{ fontSize: "0.875rem" }}>{message}</p>
    </div>
  );
}

export function FiltersFootnote({ filters }: { filters: DashboardFiltersChangedDetail }) {
  return (
    <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.75rem" }}>
      {new Date(filters.from).toLocaleDateString()} to {new Date(filters.to).toLocaleDateString()} • {filters.sourceFilter === "all" ? "All sources" : filters.sourceFilter}
    </p>
  );
}
