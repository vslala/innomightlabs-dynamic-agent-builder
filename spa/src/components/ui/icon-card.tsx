import * as React from "react";
import { cn } from "../../lib/utils";
import { Card, CardContent } from "./card";
import type { LucideIcon } from "lucide-react";

interface IconCardProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  footer?: React.ReactNode;
  actions?: React.ReactNode;
  onClick?: () => void;
  className?: string;
}

function IconCard({
  icon: Icon,
  title,
  description,
  footer,
  actions,
  onClick,
  className,
}: IconCardProps) {
  return (
    <Card
      className={cn(
        "group hover:border-[var(--gradient-start)]/50 transition-all duration-200",
        onClick && "cursor-pointer",
        className
      )}
      onClick={onClick}
    >
      <CardContent className="p-6">
        <div className="flex items-start justify-between mb-5">
          <div className="h-14 w-14 rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
            <Icon className="h-7 w-7 text-white" />
          </div>
          {actions && (
            <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              {actions}
            </div>
          )}
        </div>

        <h3 className="font-semibold text-lg text-[var(--text-primary)] mb-2 group-hover:text-[var(--gradient-start)] transition-colors">
          {title}
        </h3>
        {description && (
          <p className="text-sm text-[var(--text-muted)] line-clamp-2 mb-4 leading-relaxed">
            {description}
          </p>
        )}
        {footer}
      </CardContent>
    </Card>
  );
}

interface IconHeaderProps {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  size?: "sm" | "default" | "lg";
  className?: string;
}

function IconHeader({
  icon: Icon,
  title,
  subtitle,
  actions,
  size = "default",
  className,
}: IconHeaderProps) {
  const sizes = {
    sm: { container: "h-10 w-10 rounded-lg", icon: "h-5 w-5", title: "text-base", subtitle: "text-xs" },
    default: { container: "h-12 w-12 rounded-xl", icon: "h-6 w-6", title: "text-xl", subtitle: "text-sm" },
    lg: { container: "h-14 w-14 rounded-xl", icon: "h-7 w-7", title: "text-2xl", subtitle: "text-base" },
  };

  const s = sizes[size];

  return (
    <div className={cn("flex items-center justify-between", className)}>
      <div className="flex items-center gap-4">
        <div
          className={cn(
            "bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center",
            s.container
          )}
        >
          <Icon className={cn("text-white", s.icon)} />
        </div>
        <div>
          <h1 className={cn("font-semibold text-[var(--text-primary)]", s.title)}>
            {title}
          </h1>
          {subtitle && (
            <p className={cn("text-[var(--text-muted)]", s.subtitle)}>
              {subtitle}
            </p>
          )}
        </div>
      </div>
      {actions}
    </div>
  );
}

export { IconCard, IconHeader };
