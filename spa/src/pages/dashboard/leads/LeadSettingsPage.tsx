import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Plus, Save, Trash2 } from "lucide-react";
import {
  Alert,
  AlertDescription,
  Button,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Spinner,
} from "../../../components/ui";
import { leadsApiService } from "../../../services/leads";
import type { LeadStage, LeadStatus, LeadUsage } from "../../../types/leads";
import { leadsErrorMessage } from "./errors";
import styles from "./Leads.module.css";

const STAGES: { value: LeadStage; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "won", label: "Won" },
  { value: "lost", label: "Lost" },
];

/** The account's lead statuses and how much of the plan Leads uses this month. */
export function LeadSettingsPage() {
  const [savedKeys, setSavedKeys] = useState<string[]>([]);
  const [statuses, setStatuses] = useState<LeadStatus[] | null>(null);
  const [replacements, setReplacements] = useState<Record<string, string>>({});
  const [usage, setUsage] = useState<LeadUsage | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    leadsApiService.getSettings()
      .then((settings) => {
        setStatuses(settings.statuses);
        setSavedKeys(settings.statuses.map((status) => status.key));
      })
      .catch((err) => setError(leadsErrorMessage(err, "Statuses couldn't be loaded.")));
    leadsApiService.getUsage().then(setUsage).catch(() => undefined); // Admins only; members just don't see it
  }, []);

  if (!statuses) {
    return error
      ? <Alert variant="error"><AlertDescription>{error}</AlertDescription></Alert>
      : <p role="status" className={styles.muted}><Spinner size="sm" aria-hidden="true" /> Loading settings…</p>;
  }

  const keys = statuses.map((status) => status.key);
  const removed = savedKeys.filter((key) => !keys.includes(key));
  const update = (index: number, change: Partial<LeadStatus>) =>
    setStatuses(statuses.map((status, at) => (at === index ? { ...status, ...change } : status)));
  const move = (index: number, by: -1 | 1) => {
    const next = [...statuses];
    [next[index], next[index + by]] = [next[index + by], next[index]];
    setStatuses(next);
  };
  const add = () => {
    let key = "status";
    for (let n = 2; keys.includes(key); n++) key = `status_${n}`;
    setStatuses([...statuses, { key, label: "New status", stage: "open" }]);
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await leadsApiService.updateSettings({
        statuses,
        replacements: Object.fromEntries(removed.filter((key) => replacements[key]).map((key) => [key, replacements[key]])),
      });
      setStatuses(saved.statuses);
      setSavedKeys(saved.statuses.map((status) => status.key));
      setReplacements({});
      setNotice("Statuses saved.");
    } catch (err) {
      setError(leadsErrorMessage(err, "Statuses couldn't be saved."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={styles.content} aria-labelledby="lead-settings-heading">
      {usage && (
        <div className={styles.usage}>
          <UsageCard label="Active forms" used={usage.forms} limit={usage.forms_limit} />
          <UsageCard label="Leads this month" used={usage.captures} limit={usage.captures_limit} />
        </div>
      )}

      <div className={styles.toolbar}>
        <div>
          <h2 id="lead-settings-heading" className={styles.heading}>Statuses</h2>
          <p className={styles.muted}>New leads get the first status. The stage groups your statuses into open, won and lost.</p>
        </div>
        <Button type="button" size="sm" disabled={busy} onClick={() => void save()}><Save aria-hidden="true" />Save</Button>
      </div>
      {error && <Alert variant="error"><AlertDescription>{error}</AlertDescription></Alert>}
      {notice && <Alert variant="success" role="status"><AlertDescription>{notice}</AlertDescription></Alert>}

      <div className={styles.panel}>
        <div className={styles.panelBody}>
          {statuses.map((status, index) => (
            <div key={status.key} className={styles.statusRow}>
              <Input aria-label={`Label for ${status.key}`} value={status.label} onChange={(e) => update(index, { label: e.target.value })} />
              <Select value={status.stage} onValueChange={(stage) => update(index, { stage: stage as LeadStage })}>
                <SelectTrigger aria-label={`Stage for ${status.label}`}><SelectValue /></SelectTrigger>
                <SelectContent>
                  {STAGES.map((stage) => <SelectItem key={stage.value} value={stage.value}>{stage.label}</SelectItem>)}
                </SelectContent>
              </Select>
              <div className={styles.actions}>
                <Button type="button" variant="ghost" size="icon" aria-label={`Move ${status.label} up`} disabled={index === 0}
                  onClick={() => move(index, -1)}><ArrowUp aria-hidden="true" /></Button>
                <Button type="button" variant="ghost" size="icon" aria-label={`Move ${status.label} down`}
                  disabled={index === statuses.length - 1} onClick={() => move(index, 1)}><ArrowDown aria-hidden="true" /></Button>
                <Button type="button" variant="ghost" size="icon" aria-label={`Remove ${status.label}`} disabled={statuses.length === 1}
                  onClick={() => setStatuses(statuses.filter((_, at) => at !== index))}><Trash2 aria-hidden="true" /></Button>
              </div>
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" onClick={add}><Plus aria-hidden="true" />Add status</Button>
        </div>
      </div>

      {removed.length > 0 && (
        <div className={styles.panel}>
          <div className={styles.panelBody}>
            <p className={styles.muted}>Leads that still have a removed status move to the one you pick.</p>
            {removed.map((key) => (
              <div key={key} className={styles.statusRow}>
                <span className={styles.mono}>{key}</span>
                <Select value={replacements[key] ?? ""} onValueChange={(replacement) => setReplacements({ ...replacements, [key]: replacement })}>
                  <SelectTrigger aria-label={`Move leads from ${key} to`}><SelectValue placeholder="Move them to…" /></SelectTrigger>
                  <SelectContent>
                    {statuses.map((status) => <SelectItem key={status.key} value={status.key}>{status.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function UsageCard({ label, used, limit }: { label: string; used: number; limit: number }) {
  return (
    <div className={styles.panel}>
      <div className={styles.panelBody}>
        <span className={styles.muted}>{label}</span>
        <span className={styles.heading}>{used}{limit ? ` of ${limit}` : ""}</span>
        {!limit && <span className={styles.muted}>Unlimited on your plan</span>}
      </div>
    </div>
  );
}
