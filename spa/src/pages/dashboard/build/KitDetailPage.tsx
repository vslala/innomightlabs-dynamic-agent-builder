import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BookOpen,
  Bot,
  ExternalLink,
  History,
  MessageSquare,
  MessagesSquare,
  Package,
  Plug,
  RotateCcw,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import {
  Alert,
  AlertDescription,
  Button,
  Panel,
  PanelBody,
  PanelDescription,
  PanelHeader,
  PanelTitle,
  Spinner,
  StatusBadge,
} from "../../../components/ui";
import { kitApiService, type KitDetail, type KitPlan, type KitVersion } from "../../../services/kits/KitApiService";
import { DEPLOYMENT_STATUS } from "../blueprints/blueprintView";
import { canRollBackTo, kindName, kitContents, kitStatus, versionLabel } from "./kitView";
import { KitPlanDialog } from "./KitPlanDialog";
import styles from "./KitDetailPage.module.css";

const KIND_ICONS: Record<string, LucideIcon> = {
  Agent: Bot,
  KnowledgeBase: BookOpen,
  WidgetKey: MessagesSquare,
  McpConnection: Plug,
};

/** What the dialog is about: going back to a version, or removing the whole kit. */
type Pending = { kind: "rollback"; version: number } | { kind: "remove" };

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

export function KitDetailPage() {
  const { kitId = "" } = useParams<{ kitId: string }>();
  const [kit, setKit] = useState<KitDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [plan, setPlan] = useState<KitPlan | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);

  const load = useCallback(() => {
    kitApiService
      .getKit(kitId)
      .then((loaded) => {
        setKit(loaded);
        setLoadError(null);
      })
      .catch((err) => setLoadError(errorMessage(err, "Couldn't load this kit.")));
  }, [kitId]);

  useEffect(load, [load]);

  const openPlan = async (next: Pending) => {
    setPending(next);
    setPlan(null);
    setPlanError(null);
    try {
      setPlan(next.kind === "remove" ? await kitApiService.planRemoval(kitId) : await kitApiService.planRollback(kitId, next.version));
    } catch (err) {
      setPlanError(errorMessage(err, "Couldn't work out what would change."));
    }
  };

  const confirm = async () => {
    if (!pending || !plan?.plan_id) return;
    setApplying(true);
    try {
      if (pending.kind === "remove") {
        await kitApiService.remove(kitId, plan.plan_id);
        setNotice("The kit was removed, and everything it held was deleted.");
      } else {
        await kitApiService.rollback(kitId, pending.version, plan.plan_id);
        setNotice(`Rolled back to version ${pending.version}.`);
      }
      setPending(null);
      load();
    } catch (err) {
      setPlanError(errorMessage(err, "That didn't work. Nothing was changed."));
    } finally {
      setApplying(false);
    }
  };

  if (loadError) {
    return (
      <div className={styles.page}>
        <BackLink />
        <Alert variant="error">
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
      </div>
    );
  }
  if (!kit) {
    return (
      <div className={styles.loading}>
        <Spinner />
      </div>
    );
  }

  const status = kitStatus(kit);
  const active = kit.status === "active";

  return (
    <div className={styles.page}>
      <BackLink />
      <header className={styles.header}>
        <Package className={styles.headerIcon} aria-hidden="true" />
        <div className={styles.headerText}>
          <div className={styles.titleRow}>
            <h2 className={styles.title}>{kit.title}</h2>
            <StatusBadge status={status.status} label={status.label} />
          </div>
          {kit.description && <p className={styles.subtitle}>{kit.description}</p>}
          <p className={styles.muted}>
            {kitContents(kit.counts)} · {kit.versions} version{kit.versions === 1 ? "" : "s"}
          </p>
        </div>
        {kit.conversation_id && (
          <Button asChild variant="outline" size="sm">
            <Link to={`/dashboard/conversations/${kit.conversation_id}`}>
              <MessageSquare aria-hidden="true" /> Continue with Ila
            </Link>
          </Button>
        )}
      </header>

      {notice && (
        <Alert>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      )}

      <div className={styles.columns}>
        <Panel>
          <PanelHeader>
            <PanelTitle>What it holds</PanelTitle>
            <PanelDescription>Changed together, rolled back together, removed together.</PanelDescription>
          </PanelHeader>
          <PanelBody>
            {kit.resources.length === 0 ? (
              <p className={styles.muted}>Nothing: everything it held was removed.</p>
            ) : (
              <ul className={styles.resources}>
                {kit.resources.map((resource) => {
                  const Icon = KIND_ICONS[resource.kind] ?? Package;
                  const body = (
                    <>
                      <Icon className={styles.resourceIcon} aria-hidden="true" />
                      <span className={styles.resourceTitle}>{resource.title}</span>
                      <span className={styles.muted}>{kindName(resource.kind)}</span>
                      {resource.dashboard_path && <ExternalLink className={styles.resourceLinkIcon} aria-hidden="true" />}
                    </>
                  );
                  return (
                    <li key={resource.name}>
                      {resource.dashboard_path ? (
                        <Link to={resource.dashboard_path} className={styles.resource}>
                          {body}
                        </Link>
                      ) : (
                        <div className={styles.resource}>{body}</div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader>
            <PanelTitle>
              <History className={styles.inlineIcon} aria-hidden="true" /> Versions
            </PanelTitle>
            <PanelDescription>Go back to any version; you'll see what changes before anything happens.</PanelDescription>
          </PanelHeader>
          <PanelBody>
            <ol className={styles.timeline}>
              {kit.history.map((version) => (
                <VersionRow
                  key={version.deployment_id}
                  version={version}
                  canRollBack={canRollBackTo(version, kit)}
                  onRollBack={() => openPlan({ kind: "rollback", version: version.version })}
                />
              ))}
            </ol>
          </PanelBody>
        </Panel>
      </div>

      {active && (
        <Panel className={styles.danger}>
          <PanelHeader>
            <PanelTitle>Remove this kit</PanelTitle>
            <PanelDescription>
              Deletes everything it holds: its agents with their conversations, its knowledge bases with their content,
              its chat widgets. Connections to other services stay on your account. Its history stays here.
            </PanelDescription>
          </PanelHeader>
          <PanelBody>
            <Button variant="destructive" onClick={() => openPlan({ kind: "remove" })}>
              <Trash2 aria-hidden="true" /> Remove kit…
            </Button>
          </PanelBody>
        </Panel>
      )}

      <KitPlanDialog
        open={pending !== null}
        onOpenChange={(open) => !open && setPending(null)}
        title={pending?.kind === "remove" ? `Remove ${kit.title}?` : `Roll back to version ${pending?.kind === "rollback" ? pending.version : ""}?`}
        description={
          pending?.kind === "remove"
            ? "Everything below is deleted. Nothing happens until you confirm."
            : "The kit goes back to how that version declared it. Nothing happens until you confirm."
        }
        plan={plan}
        error={planError}
        confirmLabel={pending?.kind === "remove" ? "Remove everything" : "Roll back"}
        destructive={pending?.kind === "remove"}
        applying={applying}
        onConfirm={confirm}
      />
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/dashboard/build" className={styles.back}>
      <ArrowLeft aria-hidden="true" /> Build with Ila
    </Link>
  );
}

interface VersionRowProps {
  version: KitVersion;
  canRollBack: boolean;
  onRollBack: () => void;
}

function VersionRow({ version, canRollBack, onRollBack }: VersionRowProps) {
  const outcome = DEPLOYMENT_STATUS[version.status];
  return (
    <li className={styles.version} aria-current={version.current ? "true" : undefined}>
      <span className={styles.versionDot} data-current={version.current || undefined} aria-hidden="true" />
      <div className={styles.versionBody}>
        <div className={styles.versionHead}>
          <span className={styles.versionNumber}>v{version.version}</span>
          <span>{versionLabel(version)}</span>
          {version.current && <StatusBadge size="sm" status="active" label="Current" />}
          {version.status !== "applied" && <StatusBadge size="sm" status={outcome.status} label={outcome.label} />}
          <span className={styles.versionDate}>{new Date(version.created_at).toLocaleString()}</span>
        </div>
        {version.steps.length > 0 && (
          <details className={styles.versionSteps}>
            <summary>{version.steps.length} step{version.steps.length === 1 ? "" : "s"}</summary>
            <ul>
              {version.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ul>
          </details>
        )}
        {version.error && <p className={styles.versionError}>{version.error}</p>}
        {canRollBack && (
          <Button variant="outline" size="sm" onClick={onRollBack} className={styles.rollBack}>
            <RotateCcw aria-hidden="true" /> Roll back to this
          </Button>
        )}
      </div>
    </li>
  );
}
