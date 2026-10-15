import * as React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { FileText, Inbox, Settings2, UserPlus } from "lucide-react";
import { Page, PageBody } from "../../../components/layout";
import styles from "./Leads.module.css";

const SECTIONS = [
  { to: "/dashboard/leads", end: true, icon: Inbox, label: "Leads" },
  { to: "/dashboard/leads/forms", end: false, icon: FileText, label: "Forms" },
  { to: "/dashboard/leads/settings", end: false, icon: Settings2, label: "Settings" },
];

export function LeadsLayout(): React.JSX.Element {
  return (
    <Page>
      <div className={styles.top}>
        <header className={styles.header}>
          <span className={styles.headerIcon} aria-hidden="true"><UserPlus /></span>
          <div>
            <h1 className={styles.title}>Leads</h1>
            <p className={styles.description}>
              What your agents capture from the people they talk to, and the forms they capture with.
            </p>
          </div>
        </header>
        <nav aria-label="Leads" className={styles.navigation}>
          {SECTIONS.map(({ to, end, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => (isActive ? `${styles.navigationLink} ${styles.activeLink}` : styles.navigationLink)}
            >
              <Icon aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
      <PageBody>
        <Outlet />
      </PageBody>
    </Page>
  );
}
