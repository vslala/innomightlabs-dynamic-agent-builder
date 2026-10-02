import type { ReactNode } from "react";
import { X } from "lucide-react";

interface HeaderProps {
  agentName: string;
  subtitle: string;
  /** Extra buttons shown before the close button. */
  actions?: ReactNode;
  onClose?: () => void;
}

export function AgentAvatar({ name, large = false }: { name: string; large?: boolean }) {
  return (
    <span className={large ? "ie-avatar ie-avatar-large" : "ie-avatar"} aria-hidden="true">
      {name.trim().charAt(0).toUpperCase() || "A"}
    </span>
  );
}

export function Header({ agentName, subtitle, actions, onClose }: HeaderProps) {
  return (
    <header className="ie-header">
      <AgentAvatar name={agentName} />
      <div className="ie-header-text">
        <h1 className="ie-header-title">{agentName}</h1>
        <p className="ie-header-subtitle">{subtitle}</p>
      </div>
      <div className="ie-header-actions">
        {actions}
        {onClose && (
          <button type="button" className="ie-icon-button" aria-label="Close chat" onClick={onClose}>
            <X aria-hidden="true" />
          </button>
        )}
      </div>
    </header>
  );
}
