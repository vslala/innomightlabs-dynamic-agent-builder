import { Bell } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar";
import { Button } from "../ui/button";

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
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-dark)]/95 backdrop-blur-md px-6">
      <h1 className="text-lg font-semibold text-[var(--text-primary)]">
        {title}
      </h1>

      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" className="relative h-8 w-8">
          <Bell className="h-4 w-4" />
          <span className="absolute -top-0.5 -right-0.5 h-3.5 w-3.5 rounded-full bg-[var(--gradient-start)] text-[9px] font-medium flex items-center justify-center">
            3
          </span>
        </Button>

        {user && (
          <div className="flex items-center gap-2.5 pl-3 border-l border-[var(--border-subtle)]">
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
          </div>
        )}
      </div>
    </header>
  );
}
