import * as React from "react";
import { ArrowLeft, CheckCircle2, Info, KeyRound, LayoutGrid, Plus, RotateCw, ShieldCheck, ShieldOff, Trash2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "../../../components/ui/alert";
import { Button } from "../../../components/ui/button";
import { InlineEmptyState } from "../../../components/ui/empty-state";
import { JsonTreeViewer } from "../../../components/ui/json-viewer";
import { Label } from "../../../components/ui/label";
import { LinkButton } from "../../../components/ui/link-button";
import { ListRow } from "../../../components/ui/list-row";
import { Pill } from "../../../components/ui/pill";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../../components/ui/select";
import { Spinner } from "../../../components/ui/spinner";
import type { EffectivePolicy, PolicySummary, ServiceAccess } from "../../../services/iam";
import { accessLines, attachable, SERVICE_LEVEL_LABEL, sourceLabel } from "./describeAccess";
import type { MemberPermissionsData } from "./loadMemberPermissions";
import { initials } from "./people";
import styles from "./Iam.module.css";

export type MemberPermissionsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | ({ status: "loaded" } & MemberPermissionsData);

export interface MemberPermissionsActions {
  pending: boolean;
  error?: string;
  success?: string;
  onAttach: (policy: string) => void;
  onDetach: (policy: string) => void;
}

const SERVICE_LEVEL_VARIANT = { full: "primary", limited: "secondary", none: "outline" } as const;

export function MemberPermissionsPanel({ state, onRetry, actions }: {
  state: MemberPermissionsState;
  onRetry: () => void;
  actions: MemberPermissionsActions;
}): React.JSX.Element {
  return (
    <section className={styles.content} aria-labelledby="iam-member-title" aria-busy={state.status === "loading"}>
      <LinkButton to="/dashboard/iam/members" variant="ghost" size="sm" className={styles.back}>
        <ArrowLeft aria-hidden="true" />Members
      </LinkButton>

      {state.status === "loading" && (
        <>
          <h2 id="iam-member-title" className="sr-only">Member permissions</h2>
          <p role="status" className={styles.loading}><Spinner size="sm" aria-hidden="true" />Loading permissions…</p>
        </>
      )}

      {state.status === "error" && (
        <>
          <h2 id="iam-member-title" className="sr-only">Member permissions</h2>
          <Alert variant="error" className={styles.alert}>
            <AlertTitle>Unable to load permissions</AlertTitle>
            <AlertDescription>{state.message}</AlertDescription>
            <Button type="button" variant="outline" size="sm" className={styles.alertAction} onClick={onRetry}>
              <RotateCw aria-hidden="true" />Retry
            </Button>
          </Alert>
        </>
      )}

      {state.status === "loaded" && <Loaded data={state} actions={actions} />}
    </section>
  );
}

function Loaded({ data, actions }: { data: MemberPermissionsData; actions: MemberPermissionsActions }) {
  const { member, capabilities } = data;
  const who = member.name || member.email;

  return (
    <>
      <div className={`${styles.person} ${styles.memberHeader}`}>
        <span className={`${styles.avatar} ${styles.avatarLarge}`} aria-hidden="true">{initials(who)}</span>
        <span className={styles.personText}>
          <h2 id="iam-member-title" className={`${styles.heading} ${styles.name}`}>
            {who}
            {member.is_owner && <Pill size="sm" variant="primary">Owner</Pill>}
          </h2>
          {member.name && <span className={styles.email}>{member.email}</span>}
        </span>
      </div>

      {member.is_owner && (
        <Notice>The account owner always has full access to this account. Their permissions can't be changed.</Notice>
      )}
      {!member.is_owner && !capabilities.can_manage_permissions && (
        <Notice>Read-only access. You can see this member's permissions but not change them.</Notice>
      )}
      {actions.error && (
        <Alert variant="error" className={styles.alert}><AlertDescription>{actions.error}</AlertDescription></Alert>
      )}
      {actions.success && (
        <p role="status" className={styles.success}><CheckCircle2 aria-hidden="true" />{actions.success}</p>
      )}

      {!member.is_owner && <AttachedPolicies data={data} who={who} actions={actions} />}
      <AccessByService access={data.access} who={who} />
      <PoliciesThatApply effective={data.effective} groupNames={data.groupNames} />
    </>
  );
}

function AttachedPolicies({ data, who, actions }: { data: MemberPermissionsData; who: string; actions: MemberPermissionsActions }) {
  const { member, policies, capabilities } = data;
  const editable = capabilities.can_manage_permissions;
  const descriptions = new Map(policies.map((summary) => [summary.policy, summary.description]));

  return (
    <section className={styles.panel} aria-labelledby="iam-attached-title">
      <div className={styles.panelHeader}>
        <span className={styles.panelIcon} aria-hidden="true"><KeyRound /></span>
        <div>
          <h3 id="iam-attached-title" className={styles.panelTitle}>Policies</h3>
          <p className={styles.panelDescription}>
            What {who} can do beyond what every member can. Changes apply on their next request.
          </p>
        </div>
      </div>

      {member.policies.length === 0 ? (
        <InlineEmptyState
          icon={ShieldOff}
          title="No policies attached"
          description="They have only the access every member has, shown under Access by service."
        />
      ) : (
        <ul className={styles.policyList} aria-label={`Policies attached to ${who}`}>
          {member.policies.map((ref) => (
            <li key={ref.policy}>
              <ListRow
                title={<span className={styles.name}>{ref.name}{ref.policy.startsWith("custom:") && <Pill size="sm" variant="secondary">Custom</Pill>}</span>}
                subtitle={descriptions.get(ref.policy) || undefined}
                trailing={editable && (
                  <Button type="button" variant="ghost" size="sm" className={styles.revoke} disabled={actions.pending}
                    aria-label={`Remove ${ref.name}`} onClick={() => actions.onDetach(ref.policy)}>
                    <Trash2 aria-hidden="true" />Remove
                  </Button>
                )}
              />
            </li>
          ))}
        </ul>
      )}

      {editable && <AttachForm options={attachable(policies, member.policies)} actions={actions} />}
    </section>
  );
}

function AttachForm({ options, actions }: { options: PolicySummary[]; actions: MemberPermissionsActions }) {
  const [selected, setSelected] = React.useState("");
  const chosen = options.find((option) => option.policy === selected);
  if (options.length === 0) {
    return <p className={`${styles.hint} ${styles.attachForm}`}>Every policy in this account is already attached.</p>;
  }
  return (
    <form
      className={styles.attachForm}
      onSubmit={(event) => {
        event.preventDefault();
        if (chosen && !actions.pending) {
          actions.onAttach(chosen.policy);
          setSelected("");
        }
      }}
    >
      <div className={styles.attachRow}>
        <div className={styles.field}>
          <Label htmlFor="iam-attach-policy">Add a policy</Label>
          <Select value={selected} onValueChange={setSelected} disabled={actions.pending}>
            <SelectTrigger id="iam-attach-policy" aria-describedby="iam-attach-description">
              <SelectValue placeholder="Choose a policy" />
            </SelectTrigger>
            <SelectContent>
              {options.map((option) => <SelectItem key={option.policy} value={option.policy}>{option.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <Button type="submit" disabled={!chosen || actions.pending}>
          <Plus aria-hidden="true" />{actions.pending ? "Working…" : "Attach"}
        </Button>
      </div>
      <p id="iam-attach-description" className={styles.hint}>
        {chosen?.description || "Built-in policies cover the usual roles; custom policies are the account's own."}
      </p>
    </form>
  );
}

function AccessByService({ access, who }: { access: ServiceAccess[]; who: string }) {
  return (
    <section className={styles.subsection} aria-labelledby="iam-access-title">
      <div className={styles.sectionHeader}>
        <LayoutGrid aria-hidden="true" className={styles.inlineIcon} />
        <h3 id="iam-access-title" className={styles.subheading}>Access by service</h3>
      </div>
      <p className={styles.panelDescription}>
        What {who}'s policies allow in each part of InnomightLabs. Anything shared with them adds to this.
      </p>
      <div className={styles.tableContainer}>
        <table className={`${styles.table} ${styles.accessTable}`}>
          <caption className="sr-only">Access by service for {who}</caption>
          <thead><tr><th scope="col">Service</th><th scope="col">Access</th><th scope="col">Actions</th></tr></thead>
          <tbody>{access.map((service) => <ServiceRow key={service.service} service={service} />)}</tbody>
        </table>
      </div>
    </section>
  );
}

function ServiceRow({ service }: { service: ServiceAccess }) {
  const lines = accessLines(service);
  return (
    <tr>
      <th scope="row">
        <span className={styles.personText}>
          <span className={styles.name}>{service.label}</span>
          <span className={styles.email}>{service.summary}</span>
        </span>
      </th>
      <td><Pill size="sm" variant={SERVICE_LEVEL_VARIANT[service.level]}>{SERVICE_LEVEL_LABEL[service.level]}</Pill></td>
      <td>
        {lines.length === 0 ? <span className={styles.muted}>None</span> : (
          <ul className={styles.accessLines}>
            {lines.map((line) => (
              <li key={line.label} className={line.kind === "denied" ? styles.deniedLine : undefined}>
                <span className={styles.accessLabel}>{line.label}</span>
                <span className={styles.actionChips}>
                  {line.verbs.map((verb) => <code key={verb} className={styles.actionChip}>{verb}</code>)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </td>
    </tr>
  );
}

function PoliciesThatApply({ effective, groupNames }: { effective: EffectivePolicy[]; groupNames: ReadonlyMap<string, string> }) {
  return (
    <section className={styles.subsection} aria-labelledby="iam-effective-title">
      <div className={styles.sectionHeader}>
        <ShieldCheck aria-hidden="true" className={styles.inlineIcon} />
        <h3 id="iam-effective-title" className={styles.subheading}>Policies that apply</h3>
        <Pill size="sm" variant="secondary">{effective.length}</Pill>
      </div>
      <p className={styles.panelDescription}>Where the access above comes from. A Deny always wins over an Allow.</p>
      <ul className={styles.effectiveList}>
        {effective.map((entry) => (
          <li key={`${entry.policy}-${entry.source}`} className={styles.effective}>
            <div className={styles.effectiveHeader}>
              <span className={styles.name}>{entry.name}</span>
              <span className={styles.muted}>{sourceLabel(entry.source, groupNames)}</span>
            </div>
            {entry.description && <p className={styles.hint}>{entry.description}</p>}
            <details className={styles.policyJson}>
              <summary>View JSON</summary>
              <JsonTreeViewer value={entry.document} maxHeight="20rem" />
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return <p className={styles.notice}><Info aria-hidden="true" />{children}</p>;
}
