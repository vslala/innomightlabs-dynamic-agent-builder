import * as React from "react";
import { NavLink, Outlet } from "react-router-dom";
import { ShieldCheck, Users } from "lucide-react";
import { Page, PageBody } from "../../../components/layout";
import styles from "./Iam.module.css";

export function IamLayout(): React.JSX.Element {
  return (
    <Page>
      <div className={styles.top}>
        <header className={styles.header}>
          <span className={styles.headerIcon} aria-hidden="true"><ShieldCheck /></span>
          <div>
            <h1 className={styles.title}>Identity &amp; access</h1>
            <p className={styles.description}>Who can sign in to this account, and the invitations still waiting.</p>
          </div>
        </header>
        <nav aria-label="Identity and access" className={styles.navigation}>
          <NavLink
            to="/dashboard/iam/members"
            className={({ isActive }) => isActive ? `${styles.navigationLink} ${styles.activeLink}` : styles.navigationLink}
          >
            <Users aria-hidden="true" />
            Members
          </NavLink>
        </nav>
      </div>
      <PageBody>
        <Outlet />
      </PageBody>
    </Page>
  );
}
