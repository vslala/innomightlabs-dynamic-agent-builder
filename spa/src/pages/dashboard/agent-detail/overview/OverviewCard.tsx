/** The frame every overview card shares: a titled header with optional actions, then its body. */

import type { ReactNode } from "react";

export function OverviewCard({
  id,
  title,
  meta,
  actions,
  children,
}: {
  id: string;
  title: string;
  /** Quiet text beside the title, such as a count. */
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="agent-overview-card" aria-labelledby={`${id}-title`}>
      <header className="agent-overview-card__head">
        <h2 id={`${id}-title`}>{title}</h2>
        {meta ? <span className="agent-overview-card__meta">{meta}</span> : null}
        {actions}
      </header>
      <div className="agent-overview-card__body">{children}</div>
    </section>
  );
}
