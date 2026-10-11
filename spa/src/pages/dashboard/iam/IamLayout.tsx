import * as React from "react";
import { NavLink, Outlet } from "react-router-dom";
import styles from "./Iam.module.css";

export function IamLayout(): React.JSX.Element {
  return (
    <div className={styles.layout}>
      <header>
        <h1 className={styles.title}>Identity &amp; access</h1>
        <p className={styles.description}>Members of the current account.</p>
      </header>
      <nav aria-label="Identity and access" className={styles.navigation}>
        <NavLink
          to="/dashboard/iam/members"
          className={({ isActive }) => isActive ? styles.activeLink : styles.navigationLink}
        >
          Members
        </NavLink>
      </nav>
      <Outlet />
    </div>
  );
}
