import * as React from "react";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import type { MembersData } from "./loadMembers";
import styles from "./Iam.module.css";

export type MembersState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | ({ status: "loaded" } & MembersData);

export function MembersPanel({ state, onRetry }: { state: MembersState; onRetry: () => void }): React.JSX.Element {
  return (
    <section className={styles.content} aria-labelledby="iam-members-title" aria-busy={state.status === "loading"}>
      <h2 id="iam-members-title" className={styles.heading}>Members</h2>
      {state.status === "loading" && <p role="status">Loading account access and members…</p>}
      {state.status === "error" && (
        <div className={styles.panel}>
          <div role="alert">
            <h3 className={styles.heading}>Unable to load members</h3>
            <p>{state.message}</p>
          </div>
          <Button type="button" variant="outline" onClick={onRetry}>Retry</Button>
        </div>
      )}
      {state.status === "loaded" && (
        <>
          {!state.capabilities.can_list_members && (
            <p className={styles.notice}>
              {state.capabilities.can_invite
                ? "You can invite members, but you do not have access to the member list."
                : "Member access is unavailable. You do not have permission to list or invite members in this account."}
            </p>
          )}
          {state.capabilities.can_list_members && (
            <>
              {!state.capabilities.can_invite && (
                <p className={styles.notice}>Read-only access. You can view members but do not have permission to invite them.</p>
              )}
              {state.members.length === 0 ? (
                <p className={styles.panel}>No members found in this account.</p>
              ) : (
                <div className={styles.tableContainer}>
                  <table className={styles.table}>
                    <caption className={styles.caption}>Current account members</caption>
                    <thead><tr><th scope="col">Member</th><th scope="col">Status</th><th scope="col">Joined</th></tr></thead>
                    <tbody>
                      {state.members.map((member) => (
                        <tr key={member.user_id}>
                          <th scope="row">
                            <span>{member.name || member.email}</span>
                            {member.is_owner && <span className={styles.owner}>Owner</span>}
                            <span className={styles.email}>{member.email}</span>
                          </th>
                          <td>{member.status || "Unknown"}</td>
                          <td>{member.joined_at ? <time dateTime={member.joined_at}>{member.joined_at}</time> : "Not available"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
          {state.capabilities.can_invite && (
            <section className={styles.panel} aria-labelledby="iam-invite-title">
              <h3 id="iam-invite-title" className={styles.heading}>Invite a member</h3>
              <p id="iam-invite-notice" className={styles.description}>
                Invitation delivery is not available yet (Phase 2). No invitation will be sent, and this email is not saved.
              </p>
              <form
                className={styles.inviteForm}
                onSubmit={(event) => event.preventDefault()}
                onKeyDown={(event) => { if (event.key === "Enter") event.preventDefault(); }}
              >
                <div className={styles.field}>
                  <Label htmlFor="iam-invite-email">Email address</Label>
                  <Input id="iam-invite-email" name="email" type="email" aria-describedby="iam-invite-notice" />
                </div>
                <Button type="submit" disabled aria-describedby="iam-invite-notice">Send invitation</Button>
              </form>
            </section>
          )}
        </>
      )}
    </section>
  );
}
