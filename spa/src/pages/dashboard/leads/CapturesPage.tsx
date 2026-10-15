import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Inbox, Lock } from "lucide-react";
import {
  Alert,
  AlertDescription,
  Button,
  InlineEmptyState,
  LinkButton,
  Pill,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
  Switch,
} from "../../../components/ui";
import { agentApiService } from "../../../services/agents/AgentApiService";
import { leadsApiService } from "../../../services/leads";
import type { Capture, CaptureFilters, CapturePage, LeadForm, LeadStatus } from "../../../types/leads";
import { CaptureDetail } from "./CaptureDetail";
import { leadsErrorMessage } from "./errors";
import { captureHeadline, filtersFromSearch, formatWhen, searchFromFilters } from "./leads";
import styles from "./Leads.module.css";

const ALL = "all";

interface Choices {
  agents: { id: string; name: string }[];
  forms: LeadForm[];
  statuses: LeadStatus[];
}

export function CapturesPage() {
  const [search, setSearch] = useSearchParams();
  const filters = useMemo(() => filtersFromSearch(search), [search]);
  const [choices, setChoices] = useState<Choices>({ agents: [], forms: [], statuses: [] });
  const [page, setPage] = useState<CapturePage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([agentApiService.listAgents(), leadsApiService.listForms(), leadsApiService.getSettings()])
      .then(([agents, forms, settings]) => setChoices({
        agents: agents.map((agent) => ({ id: agent.agent_id, name: agent.agent_name })),
        forms,
        statuses: settings.statuses,
      }))
      .catch(() => undefined); // The filters just stay empty; the list below reports its own failure
  }, []);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(null);
    leadsApiService.listCaptures(filters)
      .then((loaded) => { if (current) setPage(loaded); })
      .catch((err) => { if (current) setError(leadsErrorMessage(err, "Leads couldn't be loaded.")); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [filters]);

  const filterBy = (change: Partial<CaptureFilters>) => {
    setSelectedId(null);
    setSearch(searchFromFilters({ ...filters, ...change }));
  };

  const loadMore = async () => {
    if (!page?.next_cursor) return;
    setLoading(true);
    try {
      const more = await leadsApiService.listCaptures(filters, page.next_cursor);
      setPage({ ...more, items: [...page.items, ...more.items] });
    } catch (err) {
      setError(leadsErrorMessage(err, "More leads couldn't be loaded."));
    } finally {
      setLoading(false);
    }
  };

  const replace = (updated: Capture) =>
    setPage((current) => current && { ...current, items: current.items.map((item) => (item.capture_id === updated.capture_id ? updated : item)) });
  const forget = (captureId: string) => {
    setSelectedId(null);
    setPage((current) => current && { ...current, items: current.items.filter((item) => item.capture_id !== captureId) });
  };

  const captures = page?.items ?? [];
  const selected = captures.find((capture) => capture.capture_id === selectedId) ?? null;
  const agentName = (agentId: string) => choices.agents.find((agent) => agent.id === agentId)?.name ?? "Unknown agent";
  const statusLabel = (key: string) => choices.statuses.find((status) => status.key === key)?.label ?? key;

  return (
    <section className={styles.content} aria-labelledby="leads-heading" aria-busy={loading}>
      <div className={styles.toolbar}>
        <h2 id="leads-heading" className={styles.heading}>Leads</h2>
        <div className={styles.filters}>
          <FilterSelect label="Agent" value={filters.agent_id} onChange={(agent_id) => filterBy({ agent_id })}
            options={choices.agents.map((agent) => ({ value: agent.id, label: agent.name }))} />
          <FilterSelect label="Form" value={filters.form} onChange={(form) => filterBy({ form })}
            options={choices.forms.map((form) => ({ value: form.slug, label: form.name }))} />
          <FilterSelect label="Status" value={filters.status} onChange={(status) => filterBy({ status })}
            options={choices.statuses.map((status) => ({ value: status.key, label: status.label }))} />
          <label className={styles.toggle}>
            <Switch checked={Boolean(filters.include_tests)} aria-label="Show test leads"
              onCheckedChange={(include_tests) => filterBy({ include_tests })} />
            Test leads
          </label>
        </div>
      </div>

      {page && page.locked_count > 0 && (
        <Alert variant="warning">
          <AlertDescription>
            <Lock aria-hidden="true" /> {page.locked_count} more lead{page.locked_count === 1 ? "" : "s"} came in after your
            plan's monthly limit. They are kept, and you'll see them once you upgrade.
          </AlertDescription>
          <LinkButton to="/pricing" size="sm">Upgrade</LinkButton>
        </Alert>
      )}
      {error && <Alert variant="error"><AlertDescription>{error}</AlertDescription></Alert>}
      {loading && !page && <p role="status" className={styles.muted}><Spinner size="sm" aria-hidden="true" /> Loading leads…</p>}
      {page && captures.length === 0 && !error && (
        <div className={styles.panel}>
          <div className={styles.panelBody}>
            <InlineEmptyState icon={Inbox} title="No leads yet"
              description="Create a form under Forms, add its macro to an agent's instructions, and install Lead Capture on that agent." />
          </div>
        </div>
      )}

      {captures.length > 0 && (
        <div className={styles.split}>
          <div className={styles.panel}>
            <ul className={styles.list} aria-label="Leads">
              {captures.map((capture) => (
                <li key={capture.capture_id}>
                  <Button type="button" variant="ghost" className={styles.rowButton} aria-current={capture.capture_id === selectedId}
                    onClick={() => setSelectedId(capture.capture_id)}>
                    <span className={styles.rowTitle}>{captureHeadline(capture)}</span>
                    <Pill size="sm" variant="secondary">{statusLabel(capture.status)}</Pill>
                    <span className={styles.rowMeta}>
                      {capture.form_name} · {agentName(capture.agent_id)} · <time dateTime={capture.created_at}>{formatWhen(capture.created_at)}</time>
                      {capture.source === "dashboard" && " · test"}
                    </span>
                  </Button>
                </li>
              ))}
            </ul>
            {page?.next_cursor && (
              <div className={styles.footer}>
                <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void loadMore()}>Load more</Button>
              </div>
            )}
          </div>
          {selected ? (
            <CaptureDetail key={selected.capture_id} capture={selected} agentName={agentName(selected.agent_id)}
              statuses={choices.statuses} onChange={replace} onDelete={forget} />
          ) : (
            <div className={styles.panel}><div className={styles.panelBody}><p className={styles.muted}>Select a lead to see everything it holds.</p></div></div>
          )}
        </div>
      )}
    </section>
  );
}

interface FilterSelectProps {
  label: string;
  value: string | undefined;
  options: { value: string; label: string }[];
  onChange: (value: string | undefined) => void;
}

function FilterSelect({ label, value, options, onChange }: FilterSelectProps) {
  return (
    <Select value={value ?? ALL} onValueChange={(next) => onChange(next === ALL ? undefined : next)}>
      <SelectTrigger className={styles.filter} aria-label={label}><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>Any {label.toLowerCase()}</SelectItem>
        {options.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}
