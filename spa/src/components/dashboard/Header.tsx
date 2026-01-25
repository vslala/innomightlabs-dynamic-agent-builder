import { Link } from "react-router-dom";
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar";

interface HeaderProps {
  title: string;
  user?: {
    name: string;
    email: string;
    picture?: string;
  };
}

export function Header({ title, user }: HeaderProps) {
  const initials = user?.name
    ?.split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <header
      className="sticky top-0 z-30 border-b border-[var(--border-subtle)] bg-[var(--bg-dark)]/95 backdrop-blur-md"
      style={{
        display: "flex",
        alignItems: "center",
        height: "4rem",
        padding: "0 1.5rem",
      }}
    >
      {/* Spacer for balance */}
      <div style={{ flex: 1 }} />

      {/* Centered title */}
      <h1 style={{ fontSize: "1.125rem", fontWeight: 600, color: "var(--text-primary)" }}>
        {title}
      </h1>

      {/* Right side actions */}
      <div style={{ flex: 1, display: "flex", justifyContent: "flex-end", alignItems: "center", gap: "0.75rem" }}>
        {user && (
          <Link
            to="/dashboard/settings"
            className="flex items-center gap-2.5 pl-3 border-l border-[var(--border-subtle)]"
          >
            <div className="text-right hidden sm:block">
              <p className="text-[13px] font-medium text-[var(--text-primary)] leading-tight">
                {user.name}
              </p>
              <p className="text-[11px] text-[var(--text-muted)] leading-tight">{user.email}</p>
            </div>
            <Avatar className="h-7 w-7">
              <AvatarImage src={user.picture} alt={user.name} />
              <AvatarFallback className="text-[10px]">{initials || "U"}</AvatarFallback>
            </Avatar>
          </Link>
        )}
      </div>
    </header>
  );
}
