import { useState } from "react";
import { Link } from "react-router-dom";
import { Bot, ChevronDown, ExternalLink, File, FileText, Files, GitBranch, List, MessageSquare, RefreshCw, Trash2, X } from "lucide-react";
import { Page, PageBody } from "../../components/layout/Page";
import { Alert, AlertDescription, AlertTitle } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Checkbox } from "../../components/ui/checkbox";
import { InlineEmptyState } from "../../components/ui/empty-state";
import { LinkButton } from "../../components/ui/link-button";
import { Pill } from "../../components/ui/pill";
import { SearchInput } from "../../components/ui/search-input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { Spinner } from "../../components/ui/spinner";
import type { ArtifactResponse } from "../../services/artifacts";
import { artifactSelectionState, type ArtifactNotification } from "./artifactDeletion";
import {
  INITIAL_ARTIFACT_LIBRARY_STATE, artifactFileBadge, artifactGroupIdentity, artifactFormatLabel, artifactOrigin, artifactOriginLabel, artifactSourceLabel,
  filterArtifacts, formatArtifactBytes, formatArtifactDate, groupArtifacts, selectVisibleArtifacts, shortArtifactId,
  type ArtifactLibraryState,
} from "./artifactLibrary";
import { EMPTY_ARTIFACT_SOURCE_NAMES, type ArtifactSourceNames } from "./artifactSources";
import styles from "./ArtifactsPage.module.css";

export interface ArtifactsPagePanelProps {
  artifacts: ArtifactResponse[];
  selected: string[];
  loading: boolean;
  error: string | null;
  locked: boolean;
  notification: ArtifactNotification | null;
  sourceNames?: ArtifactSourceNames;
  onReload: () => void;
  onDismiss: () => void;
  onSelectionChange: (ids: string[]) => void;
  onDelete: (artifact: ArtifactResponse) => void;
  onBulkDelete: () => void;
}

export function ArtifactsPagePanel(props: ArtifactsPagePanelProps) {
  const [view, setView] = useState<ArtifactLibraryState>(INITIAL_ARTIFACT_LIBRARY_STATE);
  return <ArtifactsPageContent {...props} view={view} onViewChange={(change) => setView((current) => ({ ...current, ...change }))} />;
}

interface ArtifactsPageContentProps extends ArtifactsPagePanelProps {
  view: ArtifactLibraryState;
  onViewChange: (change: Partial<ArtifactLibraryState>) => void;
}

const formatOptions = [
  ["all", "All formats"], ["html_report", "HTML reports"], ["image", "Images"], ["file", "Files"],
  ["csv", "CSV"], ["markdown", "Markdown"], ["json", "JSON"], ["text", "Text"], ["code", "Code"], ["canvas", "Canvases"],
] as const;
const sourceOptions = [["all", "All sources"], ["conversation", "Conversations"], ["automation", "Automations"], ["unknown", "Unknown source"]] as const;
const periodOptions = [["all", "Any time"], ["7", "Last 7 days"], ["30", "Last 30 days"]] as const;
const sortOptions = [["newest", "Newest first"], ["oldest", "Oldest first"], ["name", "Name A–Z"]] as const;

function LibrarySelect<T extends string>({ label, value, options, disabled, onChange }: {
  label: string; value: T; options: readonly (readonly [T, string])[]; disabled: boolean; onChange: (value: T) => void;
}) {
  return <Select value={value} disabled={disabled} onValueChange={(next) => {
    const option = options.find(([key]) => key === next);
    if (!disabled && option) onChange(option[0]);
  }}>
    <SelectTrigger aria-label={label} className={styles.filterSelect}><SelectValue /></SelectTrigger>
    <SelectContent>{options.map(([key, text]) => <SelectItem key={key} value={key}>{text}</SelectItem>)}</SelectContent>
  </Select>;
}

export function ArtifactsPageContent({ artifacts, selected, loading, error, locked, notification,
  sourceNames = EMPTY_ARTIFACT_SOURCE_NAMES, onReload, onDismiss, onSelectionChange, onDelete, onBulkDelete, view, onViewChange,
}: ArtifactsPageContentProps) {
  const disabled = loading || locked;
  const visible = filterArtifacts(artifacts, view, sourceNames);
  const ids = visible.map((artifact) => artifact.artifact_id);
  const { all, mixed } = artifactSelectionState(selected, ids);
  const groups = groupArtifacts(visible, view.group, sourceNames);
  const expandedArtifacts = groups.filter((group) => !view.collapsedGroups.includes(`${view.group}:${group.id}`)).flatMap((group) => group.artifacts);
  const active = expandedArtifacts.find((artifact) => artifact.artifact_id === view.activeId) ?? expandedArtifacts[0];
  const hiddenSelected = selected.filter((id) => !ids.includes(id)).length;
  const metrics = [
    { icon: Files, count: artifacts.length, label: "artifacts" },
    { icon: Bot, count: new Set(artifacts.flatMap((artifact) => artifact.source.agent_id ? [artifact.source.agent_id] : [])).size, label: "agents" },
    { icon: GitBranch, count: new Set(artifacts.flatMap((artifact) => artifact.source.automation_id ? [artifact.source.automation_id] : [])).size, label: "automations" },
    { icon: MessageSquare, count: new Set(artifacts.flatMap((artifact) => artifact.source.conversation_id ? [artifact.source.conversation_id] : [])).size, label: "conversations" },
  ];
  const updateView = (change: Partial<ArtifactLibraryState>) => { if (!disabled) onViewChange(change); };
  const inspect = (artifact: ArtifactResponse) => <ArtifactDetails artifact={artifact} names={sourceNames} />;

  return (
    <Page><PageBody>
      <section className={styles.content} aria-labelledby="artifacts-heading" aria-busy={loading || locked}>
        <div className={styles.header}>
          <div><div className={styles.headingGroup}><h1 id="artifacts-heading" className={styles.heading}>Artifacts</h1></div>
            <p className={styles.subtitle}>Everything your agents create, with the context behind it.</p></div>
          <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => { if (!disabled) onReload(); }}><RefreshCw aria-hidden="true" />Reload</Button>
        </div>
        {notification && <Alert variant={notification.variant} role={notification.variant === "success" ? "status" : "alert"}
          aria-live={notification.variant === "success" ? "polite" : "assertive"} aria-atomic="true" className={styles.notification}>
          <AlertDescription>{notification.message}</AlertDescription>
          <Button type="button" variant="ghost" size="icon" aria-label="Dismiss notification" onClick={onDismiss}><X aria-hidden="true" /></Button>
        </Alert>}
        {loading && <p role="status" className={styles.loading}><Spinner size="sm" aria-hidden="true" />Loading artifacts…</p>}
        {error && <Alert variant="error" className={styles.error}><AlertTitle>Artifacts unavailable</AlertTitle><AlertDescription>{error}</AlertDescription>
          <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => { if (!disabled) onReload(); }}><RefreshCw aria-hidden="true" />Retry</Button>
        </Alert>}
        {!loading && !error && artifacts.length === 0 && <div className={styles.empty}><InlineEmptyState icon={FileText} title="No artifacts yet" description="Generated reports and files will appear here after an agent or automation creates them." /></div>}
        {artifacts.length > 0 && <>
          <div className={styles.metrics} aria-label="Loaded library summary">{metrics.map(({ icon: Icon, count, label }) => <div key={label}><Icon aria-hidden="true" /><strong>{count}</strong><span>{label}</span></div>)}</div>
          <div className={styles.filters} role="search" aria-label="Filter loaded artifacts">
            <div className={styles.search}><SearchInput aria-label="Search artifacts and sources" placeholder="Search files, agents, conversations…" value={view.query} disabled={disabled} onChange={(event) => updateView({ query: event.target.value })} /></div>
            <LibrarySelect label="Artifact format" value={view.format} options={formatOptions} disabled={disabled} onChange={(format) => updateView({ format })} />
            <LibrarySelect label="Creation source" value={view.source} options={sourceOptions} disabled={disabled} onChange={(source) => updateView({ source })} />
            <LibrarySelect label="Creation date" value={view.period} options={periodOptions} disabled={disabled} onChange={(period) => updateView({ period })} />
          </div>
          <div className={styles.viewbar}>
            <div className={styles.grouping} role="group" aria-label="Group artifacts">{([
              ["agent", "By agent", Bot], ["automation", "By automation", GitBranch], ["none", "All files", List],
            ] as const).map(([group, label, Icon]) => <Button key={group} type="button" variant={view.group === group ? "secondary" : "ghost"} size="sm" aria-pressed={view.group === group} disabled={disabled} onClick={() => updateView({ group })}><Icon aria-hidden="true" />{label}</Button>)}</div>
            <div className={styles.resultControls}><span role="status" aria-live="polite">{visible.length} of {artifacts.length} loaded</span><LibrarySelect label="Sort artifacts" value={view.sort} options={sortOptions} disabled={disabled} onChange={(sort) => updateView({ sort })} /></div>
          </div>
          <div className={styles.library}>
            <div className={styles.results}>
              <div className={styles.toolbar} data-has-selection={selected.length > 0}>
                <label className={styles.selectAll}><Checkbox checked={all} aria-checked={mixed ? "mixed" : all} disabled={disabled || ids.length === 0}
                  ref={(node) => { if (node) node.indeterminate = mixed; }} onChange={(event) => { if (!disabled) onSelectionChange(selectVisibleArtifacts(selected, ids, event.currentTarget.checked)); }} />Select visible artifacts</label>
                <div className={styles.actions}><span className={styles.selectedCount}>{selected.length} selected{hiddenSelected > 0 && ` (${hiddenSelected} hidden by filters)`}</span>
                  {selected.length > 0 && <Button type="button" variant="ghost" size="sm" disabled={disabled} onClick={() => { if (!disabled) onSelectionChange([]); }}>Clear selection</Button>}
                  <Button type="button" variant="outline" size="sm" disabled={disabled || selected.length === 0} onClick={() => { if (!disabled && selected.length > 0) onBulkDelete(); }}><Trash2 aria-hidden="true" />Delete selected</Button>
                </div>
              </div>
              {visible.length === 0 && <div className={styles.empty}><InlineEmptyState icon={Files} title="No matching artifacts" description="Try a different search, format, source, or date range." /><Button type="button" variant="outline" size="sm" disabled={disabled} onClick={() => updateView({ query: "", format: "all", source: "all", period: "all" })}>Clear filters</Button></div>}
              {groups.map((group) => {
                const identity = artifactGroupIdentity(group.id, group.title);
                return <details data-artifact-group key={`${view.group}:${group.id}`} className={styles.panel} open={!view.collapsedGroups.includes(`${view.group}:${group.id}`)}>
                <summary className={styles.groupHeader} onClick={(event) => {
                  event.preventDefault();
                  const key = `${view.group}:${group.id}`;
                  updateView({ collapsedGroups: view.collapsedGroups.includes(key) ? view.collapsedGroups.filter((id) => id !== key) : [...view.collapsedGroups, key] });
                }}><span className={styles.avatar} data-tone={identity.tone} aria-hidden="true">{view.group === "agent" ? identity.initials : view.group === "automation" ? <GitBranch /> : <Files />}</span>
                  <span className={styles.groupInfo}><span className={styles.groupTitle}>{group.title}<Pill size="sm" variant="secondary">{group.artifacts.length}</Pill></span><span className={styles.groupDescription}>{group.description}</span></span><ChevronDown className={styles.chevron} aria-hidden="true" />
                </summary>
                <ul className={styles.list} aria-label={`${group.title} artifacts`}>{group.artifacts.map((artifact) => {
                  const isActive = active?.artifact_id === artifact.artifact_id;
                  const origin = artifactOrigin(artifact);
                  const OriginIcon = origin === "automation" ? GitBranch : origin === "conversation" ? MessageSquare : File;
                  return <li key={artifact.artifact_id} className={`${styles.row} ${isActive ? styles.activeRow : ""}`}>
                    <Checkbox aria-label={`Select artifact: ${artifact.title}`} checked={selected.includes(artifact.artifact_id)} disabled={disabled} onChange={(event) => {
                      if (!disabled) onSelectionChange(selectVisibleArtifacts(selected, [artifact.artifact_id], event.currentTarget.checked));
                    }} />
                    <ArtifactFileTile artifact={artifact} />
                    <div className={styles.details}>
                      <Button type="button" variant="ghost" className={styles.artifactTitle} aria-label={`Show details: ${artifact.title}`} aria-pressed={isActive} disabled={disabled} onClick={() => updateView({ activeId: artifact.artifact_id })}>{artifact.title}</Button>
                      <p className={styles.origin} data-origin={origin}><OriginIcon aria-hidden="true" /><span>{artifactOriginLabel(artifact, sourceNames)}</span>{view.group !== "agent" && <span> · {artifactSourceLabel("agents", artifact.source.agent_id, sourceNames)}</span>}</p>
                      <p className={styles.metadata}>{artifactFormatLabel(artifact.artifact_type)} · {formatArtifactBytes(artifact.size_bytes)} · <time dateTime={artifact.created_at}>{formatArtifactDate(artifact.created_at)}</time></p>
                    </div>
                    <div className={styles.rowMetadata}><time dateTime={artifact.created_at}>{Number.isNaN(Date.parse(artifact.created_at)) ? "Date unavailable" : new Date(artifact.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}</time><span>{formatArtifactBytes(artifact.size_bytes)}</span></div>
                    <div className={styles.rowActions}>
                      {artifact.view_url && <LinkButton to={`/dashboard/artifacts/${encodeURIComponent(artifact.artifact_id)}`} variant="outline" size="sm" aria-label={`Open artifact: ${artifact.title}`}><ExternalLink aria-hidden="true" /><span>Open</span></LinkButton>}
                      <Button type="button" variant="ghost" size="icon" className={styles.deleteAction} aria-label={`Delete artifact: ${artifact.title}`} disabled={disabled} onClick={() => { if (!disabled) onDelete(artifact); }}><Trash2 aria-hidden="true" /></Button>
                    </div>
                    {isActive && <div className={styles.mobileInspector}>{inspect(artifact)}</div>}
                  </li>;
                })}</ul>
              </details>;})}
            </div>
            {active && <aside className={styles.desktopInspector} aria-label="Selected artifact details">{inspect(active)}</aside>}
          </div>
          <p className={styles.scopeNote}>Showing the latest {artifacts.length} loaded artifacts (up to 100). Search, filters, and counts apply to this set.</p>
        </>}
      </section>
    </PageBody></Page>
  );
}

function ArtifactFileTile({ artifact, large = false }: { artifact: ArtifactResponse; large?: boolean }) {
  const label = artifactFileBadge(artifact);
  return <span className={`${styles.fileIcon} ${styles[artifact.artifact_type] ?? ""} ${large ? styles.largeFileIcon : ""}`} role="img" aria-label={`${label} file`}>
    <span>{label}</span>
  </span>;
}

function ArtifactDetails({ artifact, names }: { artifact: ArtifactResponse; names: ArtifactSourceNames }) {
  const source = artifact.source;
  const sourceLink = (kind: "agents" | "automations" | "conversations", id: string) => <Link to={`/dashboard/${kind}/${encodeURIComponent(id)}`} title={id}>{artifactSourceLabel(kind, id, names)}<ExternalLink aria-hidden="true" /></Link>;
  const recordedIds = [
    ["Artifact ID", artifact.artifact_id], ["Agent ID", source.agent_id], ["Automation ID", source.automation_id],
    ["Automation run", source.automation_run_id], ["Workflow step ID", source.automation_node_id],
    ["Conversation ID", source.conversation_id], ["Message ID", source.message_id], ["Skill ID", source.skill_id],
  ];
  return <section className={styles.inspector} aria-label={`Details for ${artifact.title}`}>
    <div className={styles.inspectorHeader}><h2>Artifact details</h2><span>{artifactFormatLabel(artifact.artifact_type)}</span></div>
    <div className={styles.fileCover} aria-label="File format summary">
      <ArtifactFileTile artifact={artifact} large />
      <span>{artifactFileBadge(artifact)} · {formatArtifactBytes(artifact.size_bytes)}</span>
    </div>
    <div className={styles.inspectorBody}>
      <div className={styles.fileSummary}><h3>{artifact.title}</h3><p>{artifact.filename}</p></div>
      {artifact.view_url && <LinkButton to={`/dashboard/artifacts/${encodeURIComponent(artifact.artifact_id)}`} size="sm" className={styles.openFile}><ExternalLink aria-hidden="true" />Open file</LinkButton>}
      <h3 className={styles.provenanceHeading}>Where this came from</h3>
      <dl className={styles.provenance}>
        <div><dt>Created by</dt><dd>{source.agent_id ? sourceLink("agents", source.agent_id) : "Agent not recorded"}</dd></div>
        {source.automation_id && <div><dt>Automation</dt><dd>{sourceLink("automations", source.automation_id)}{source.automation_run_id && <span className={styles.sourceNote} title={source.automation_run_id}>Run {shortArtifactId(source.automation_run_id)}</span>}</dd></div>}
        {!source.automation_id && source.automation_run_id && <div><dt>Automation run</dt><dd title={source.automation_run_id}>{shortArtifactId(source.automation_run_id)}</dd></div>}
        {source.automation_node_id && <div><dt>Workflow step</dt><dd title={source.automation_node_id}>{shortArtifactId(source.automation_node_id)}</dd></div>}
        {source.conversation_id && <div><dt>Conversation</dt><dd>{sourceLink("conversations", source.conversation_id)}</dd></div>}
        {artifactOrigin(artifact) === "unknown" && <div><dt>Origin</dt><dd>Source not recorded</dd></div>}
        <div><dt>Generated with</dt><dd>{source.skill_id && source.agent_id ? <Link to={`/dashboard/agents/${encodeURIComponent(source.agent_id)}/skills`} title={source.skill_id}>{artifactSourceLabel("skills", source.skill_id, names)}<ExternalLink aria-hidden="true" /></Link> : source.skill_id ? <span title={source.skill_id}>{artifactSourceLabel("skills", source.skill_id, names)}</span> : "Skill not recorded"}</dd></div>
      </dl>
      <dl className={styles.fileMetadata}>
        <div><dt>Created</dt><dd><time dateTime={artifact.created_at}>{formatArtifactDate(artifact.created_at)}</time></dd></div>
        <div><dt>Size</dt><dd>{formatArtifactBytes(artifact.size_bytes)}</dd></div>
      </dl>
      <details className={styles.technicalDetails}>
        <summary>Technical details<ChevronDown aria-hidden="true" /></summary>
        <dl><div><dt>Content type</dt><dd>{artifact.mime_type}</dd></div>{recordedIds.filter(([, id]) => id).map(([label, id]) => <div key={label}><dt>{label}</dt><dd><code className={styles.sourceId}>{id}</code></dd></div>)}</dl>
      </details>
    </div>
  </section>;
}
