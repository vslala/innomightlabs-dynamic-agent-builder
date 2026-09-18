import { useCallback, useEffect, useState } from "react";
import { Brain, Loader2, Play, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { AlertBanner, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, InlineEmptyState, Pill } from "../../../components/ui";
import { Inline, Stack } from "../../../components/layout";
import { dreamApiService, type DreamActionLog, type DreamCursor, type DreamRun } from "../../../services/dream";
import { useAgentDetailContext } from "./types";

const formatDate = (value: string | null) => value ? new Date(value).toLocaleString() : "—";

export function AgentDreamPage() {
  const { agent } = useAgentDetailContext();
  const [runs, setRuns] = useState<DreamRun[]>([]);
  const [cursor, setCursor] = useState<DreamCursor | null>(null);
  const [selectedRun, setSelectedRun] = useState<DreamRun | null>(null);
  const [actions, setActions] = useState<DreamActionLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [nextRuns, nextCursor] = await Promise.all([dreamApiService.listRuns(agent.agent_id), dreamApiService.getCursor(agent.agent_id)]);
      setRuns(nextRuns); setCursor(nextCursor);
      setSelectedRun(current => current && nextRuns.some(run => run.run_id === current.run_id) ? current : nextRuns[0] ?? null);
    } catch { setError("Failed to load Dream history."); } finally { setLoading(false); }
  }, [agent.agent_id]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!selectedRun) { setActions([]); return; }
    void dreamApiService.listActions(agent.agent_id, selectedRun.run_id).then(setActions).catch(() => setError("Failed to load Dream action audit."));
  }, [agent.agent_id, selectedRun]);

  const runNow = async () => {
    setRunning(true); setError(null);
    try { await dreamApiService.runNow(agent.agent_id); window.setTimeout(() => void load(), 1000); }
    catch { setError("Failed to start Dream run."); } finally { setRunning(false); }
  };

  return <Stack gap="lg">
    <Card><CardHeader><Inline justify="space-between"><div><CardTitle><Brain size={18} /> Dream</CardTitle><CardDescription>Nightly organization of durable core and archival memory.</CardDescription></div><Inline gap="sm"><Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}><RefreshCw size={14} /> Refresh</Button><Button size="sm" onClick={() => void runNow()} disabled={running}>{running ? <Loader2 size={14} /> : <Play size={14} />} Run now</Button></Inline></Inline></CardHeader><CardContent><p>Configure the dream model and schedule in <Link to="/dashboard/settings">Settings</Link>.</p>{cursor ? <p>Backfill: {cursor.backfill_completed ? "complete" : "in progress"} · {cursor.sessions_dreamed} sessions dreamed · last session {formatDate(cursor.last_session_ended_at)}</p> : <p>No completed Dream run yet.</p>}</CardContent></Card>
    {error && <AlertBanner variant="error" message={error} />}
    {loading ? <InlineEmptyState icon={Loader2} title="Loading Dream history" description="" /> : <div style={{ display: "grid", gridTemplateColumns: "minmax(18rem, 1fr) minmax(0, 2fr)", gap: "1rem" }}><Card><CardHeader><CardTitle>Recent runs</CardTitle></CardHeader><CardContent>{runs.length === 0 ? <InlineEmptyState icon={Brain} title="No Dream runs" description="Run a Dream after configuring a provider and model." /> : <Stack gap="xs">{runs.map(run => <Button key={run.run_id} variant={selectedRun?.run_id === run.run_id ? "secondary" : "ghost"} onClick={() => setSelectedRun(run)} style={{ justifyContent: "space-between" }}><span>{formatDate(run.started_at)}</span><Pill>{run.status}</Pill></Button>)}</Stack>}</CardContent></Card>
      <Card><CardHeader><CardTitle>{selectedRun ? "Run audit" : "Select a run"}</CardTitle></CardHeader><CardContent>{selectedRun ? <Stack gap="md"><p>{selectedRun.mode} · {selectedRun.sessions_dreamed} sessions dreamed · {selectedRun.sessions_remaining} remaining · {selectedRun.actions_executed} actions executed · {selectedRun.prompt_tokens + selectedRun.completion_tokens} tokens</p>{selectedRun.error && <AlertBanner variant="error" message={selectedRun.error} />}{actions.length === 0 ? <p>No proposed memory actions.</p> : actions.map(action => <div key={action.index} style={{ borderTop: "1px solid var(--border)", paddingTop: ".75rem" }}><Inline justify="space-between"><strong>{action.action_type}</strong><Pill>{action.outcome}</Pill></Inline><p>{action.content_preview || "No content"}</p><small>{action.block_name}{action.line_number ? ` · line ${action.line_number}` : ""} · {Math.round(action.confidence * 100)}% confidence</small><p>{action.reason}</p><small>{action.detail}</small></div>)}</Stack> : <p>Select a run to inspect the redacted memory action audit.</p>}</CardContent></Card></div>}
  </Stack>;
}
