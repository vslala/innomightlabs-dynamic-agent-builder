import type { ReactNode } from "react";
import { Github, Globe, Megaphone, Palette, Plug, SquareKanban } from "lucide-react";

import { Label } from "../../../components/ui";

const PROVIDER_ICONS: Record<string, typeof Plug> = {
  atlassian: SquareKanban,
  canva: Palette,
  github: Github,
  google_ads: Megaphone,
  tavily: Globe,
};

export function ProviderIcon({ icon }: { icon: string }) {
  const Icon = PROVIDER_ICONS[icon] ?? Plug;
  return <Icon className="h-5 w-5" />;
}

export function IconBox({ children, size = "2.5rem" }: { children: ReactNode; size?: string }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "0.5rem",
        display: "grid",
        placeItems: "center",
        background: "rgba(255,255,255,0.06)",
        color: "var(--text-primary)",
        flexShrink: 0,
      }}
    >
      {children}
    </div>
  );
}

export function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div style={{ display: "grid", gap: "0.5rem" }}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}

export function Hint({ children }: { children: ReactNode }) {
  return <p style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>{children}</p>;
}
