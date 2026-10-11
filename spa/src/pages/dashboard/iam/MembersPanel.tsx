import * as React from "react";
import { CheckCircle2, Info, Mail, RotateCw, Send, UserPlus, Users, XCircle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "../../../components/ui/alert";
import { Button } from "../../../components/ui/button";
import { InlineEmptyState } from "../../../components/ui/empty-state";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { Pill } from "../../../components/ui/pill";
import { Spinner } from "../../../components/ui/spinner";
import { StatusBadge } from "../../../components/ui/status-badge";
import type { Invitation } from "../../../services/iam/invitations";
import { formatRelativeTime } from "../../../utils/time";
import type { MembersData } from "./loadMembers";
import styles from "./Iam.module.css";

export type MembersState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | ({ status: "loaded" } & MembersData);

export interface MembersActions {
  pending: boolean;
  error?: string;
  success?: string;
  onInvite: (email: string) => void;
  onResend: (id: string) => void;
  onRevoke: (id: string) => void;
}

export function MembersPanel({ state, onRetry, actions }: { state: MembersState; onRetry: () => void; actions: MembersActions }): React.JSX.Element {
  const listing = state.status === "loaded" && state.capabilities.can_list_members;
  const openInvitations = state.status === "loaded"
    ? state.invitations.filter((invite) => invite.status !== "accepted" && invite.status !== "revoked")
    : [];

  return (
    <section className={styles.content} aria-labelledby="iam-members-title" aria-busy={state.status === "loading"}>
      <div className={styles.sectionHeader}>
        <h2 id="iam-members-title" className={styles.heading}>Members</h2>
        {listing && state.members.length > 0 && <Pill size="sm" variant="secondary">{state.members.length}</Pill>}
      </div>

      {state.status === "loading" && (
        <p role="status" className={styles.loading}><Spinner size="sm" aria-hidden="true" />Loading account access and members…</p>
      )}

      {state.status === "error" && (
        <Alert variant="error" className={styles.alert}>
          <AlertTitle>Unable to load members</AlertTitle>
          <AlertDescription>{state.message}</AlertDescription>
          <Button type="button" variant="outline" size="sm" className={styles.alertAction} onClick={onRetry}>
            <RotateCw aria-hidden="true" />Retry
          </Button>
        </Alert>
      )}

      {state.status === "loaded" && (
        <>
          {!state.capabilities.can_list_members && (
            <Notice>
              {state.capabilities.can_invite
                ? "You can invite members, but you do not have access to the member list."
                : "Member access is unavailable. You do not have permission to list or invite members in this account."}
            </Notice>
          )}
          {listing && !state.capabilities.can_invite && (
            <Notice>Read-only access. You can view members but do not have permission to invite them.</Notice>
          )}

          {actions.error && (
            <Alert variant="error" className={styles.alert}><AlertDescription>{actions.error}</AlertDescription></Alert>
          )}
          {actions.success && (
            <p role="status" className={styles.success}><CheckCircle2 aria-hidden="true" />{actions.success}</p>
          )}

          {state.capabilities.can_invite && (
            <section className={styles.panel} aria-labelledby="iam-invite-title">
              <div className={styles.panelHeader}>
                <span className={styles.panelIcon} aria-hidden="true"><UserPlus /></span>
                <div>
                  <h3 id="iam-invite-title" className={styles.panelTitle}>Invite a member</h3>
                  <p id="iam-invite-notice" className={styles.panelDescription}>
                    Send an invitation to join this account. The recipient must sign in with the invited email.
                  </p>
                </div>
              </div>
              <form
                className={styles.inviteForm}
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!actions.pending) actions.onInvite(String(new FormData(event.currentTarget).get("email") || "").trim());
                }}
              >
                <div className={styles.field}>
                  <Label htmlFor="iam-invite-email">Email address</Label>
                  <Input id="iam-invite-email" name="email" type="email" placeholder="name@company.com" required disabled={actions.pending} aria-describedby="iam-invite-notice" />
                </div>
                <Button type="submit" disabled={actions.pending} aria-describedby="iam-invite-notice">
                  <Send aria-hidden="true" />{actions.pending ? "Working…" : "Send invitation"}
                </Button>
              </form>
            </section>
          )}

          {listing && (
            <>
              {state.directoryError && (
                <Alert variant="error" className={styles.alert}>
                  <AlertDescription>{state.directoryError}</AlertDescription>
                  <Button type="button" variant="outline" size="sm" className={styles.alertAction} onClick={onRetry}>
                    <RotateCw aria-hidden="true" />Retry
                  </Button>
                </Alert>
              )}
              {state.members.length === 0 && !state.directoryError ? (
                <div className={styles.panel}>
                  <InlineEmptyState icon={Users} title="No members found in this account." description="Invited people appear here once they accept." />
                </div>
              ) : state.members.length > 0 && (
                <div className={styles.tableContainer}>
                  <table className={styles.table}>
                    <caption className="sr-only">Current account members</caption>
                    <thead><tr><th scope="col">Member</th><th scope="col">Status</th><th scope="col">Joined</th></tr></thead>
                    <tbody>
                      {state.members.map((member) => (
                        <tr key={member.user_id}>
                          <th scope="row">
                            <span className={styles.person}>
                              <span className={styles.avatar} aria-hidden="true">{initials(member.name || member.email)}</span>
                              <span className={styles.personText}>
                                <span className={styles.name}>
                                  {member.name || member.email}
                                  {member.is_owner && <Pill size="sm" variant="primary">Owner</Pill>}
                                </span>
                                {member.name && <span className={styles.email}>{member.email}</span>}
                              </span>
                            </span>
                          </th>
                          <td><MemberStatus status={member.status} /></td>
                          <td className={styles.muted}>
                            {member.joined_at ? <time dateTime={member.joined_at}>{formatDate(member.joined_at)}</time> : "Not available"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {openInvitations.length > 0 && (
                <section className={styles.subsection} aria-labelledby="iam-invitations-title">
                  <div className={styles.sectionHeader}>
                    <h3 id="iam-invitations-title" className={styles.subheading}>Invitations</h3>
                    <Pill size="sm" variant="secondary">{openInvitations.length}</Pill>
                  </div>
                  <div className={styles.tableContainer}>
                    <table className={styles.table}>
                      <caption className="sr-only">Account invitations</caption>
                      <thead>
                        <tr>
                          <th scope="col">Email</th><th scope="col">Status</th><th scope="col">Expires</th>
                          {state.capabilities.can_invite && <th scope="col" className={styles.actionsCell}>Actions</th>}
                        </tr>
                      </thead>
                      <tbody>{openInvitations.map((invite) => (
                        <tr key={invite.invite_id}>
                          <th scope="row">
                            <span className={styles.person}>
                              <span className={styles.avatar} aria-hidden="true"><Mail /></span>
                              <span className={styles.name}>{invite.email}</span>
                            </span>
                          </th>
                          <td><InvitationStatus invite={invite} /></td>
                          <td className={styles.muted}>
                            <time dateTime={invite.expires_at} title={formatDate(invite.expires_at)}>{formatRelativeTime(invite.expires_at)}</time>
                          </td>
                          {state.capabilities.can_invite && (
                            <td className={styles.actionsCell}>
                              <span className={styles.actions}>
                                <Button type="button" variant="outline" size="sm" disabled={actions.pending} onClick={() => actions.onResend(invite.invite_id)}>
                                  <RotateCw aria-hidden="true" />Resend
                                </Button>
                                <Button type="button" variant="ghost" size="sm" className={styles.revoke} disabled={actions.pending} onClick={() => actions.onRevoke(invite.invite_id)}>
                                  <XCircle aria-hidden="true" />Revoke
                                </Button>
                              </span>
                            </td>
                          )}
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                </section>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return <p className={styles.notice}><Info aria-hidden="true" />{children}</p>;
}

function MemberStatus({ status }: { status?: string }) {
  if (status === "active") return <StatusBadge status="active" size="sm" />;
  return <StatusBadge status="no_status" size="sm" label={status ? capitalise(status) : "Unknown"} />;
}

/** The invitation's state and its email's delivery, as words as well as colour. */
function InvitationStatus({ invite }: { invite: Invitation }) {
  return (
    <span className={styles.statusStack}>
      {invite.status === "expired"
        ? <StatusBadge status="warning" size="sm" label="Expired" />
        : <StatusBadge status="pending" size="sm" label={capitalise(invite.status)} />}
      {invite.delivery_status === "failed" && <StatusBadge status="error" size="sm" label="Delivery failed" />}
      {invite.delivery_status === "pending" && <span className={styles.muted}>Sending…</span>}
      {invite.delivery_status === "sent" && <span className={styles.muted}>Email sent</span>}
    </span>
  );
}

function initials(name: string): string {
  const words = name.split(/[\s@._-]+/).filter(Boolean);
  return words.slice(0, 2).map((word) => word[0].toUpperCase()).join("") || "?";
}

function capitalise(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
