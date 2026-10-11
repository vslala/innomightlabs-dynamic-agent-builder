import { forwardRef } from "react";
import { Link } from "react-router-dom";
import { Menu } from "lucide-react";
import { Button } from "../ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar";
import { AccountSwitcher } from "./AccountSwitcher";
import "./Header.css";

interface HeaderProps {
  title: string;
  user?: {
    name: string;
    email: string;
    picture?: string;
  };
  /** The id of the navigation drawer this header's menu button opens. */
  navigationId: string;
  navigationOpen: boolean;
  onMenuClick: () => void;
}

export const Header = forwardRef<HTMLButtonElement, HeaderProps>(function Header(
  { title, user, navigationId, navigationOpen, onMenuClick },
  menuButton,
) {
  const initials = user?.name
    ?.split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <header className="dashboard-header">
      <div className="dashboard-header__start">
        {/* Shown only where the sidebar is a drawer */}
        <Button
          type="button"
          ref={menuButton}
          variant="ghost"
          size="icon"
          className="dashboard-header__menu"
          style={{ width: "2.75rem", height: "2.75rem" }}
          aria-label="Open navigation"
          aria-controls={navigationId}
          aria-expanded={navigationOpen}
          onClick={onMenuClick}
        >
          <Menu aria-hidden="true" />
        </Button>
        {/* The account every request acts in */}
        <div className="dashboard-header__account">
          <AccountSwitcher />
        </div>
      </div>

      <h1 className="dashboard-header__title">{title}</h1>

      <div className="dashboard-header__end">
        {user && (
          <Link to="/dashboard/settings" className="dashboard-header__user">
            <div className="dashboard-header__identity">
              <p className="dashboard-header__name">{user.name}</p>
              <p className="dashboard-header__email">{user.email}</p>
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
});
