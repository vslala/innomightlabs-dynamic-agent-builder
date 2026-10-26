import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";

import { Switch } from "../../../components/ui";
import { consentApiService } from "../../../services/consent";
import type { ConsentAction } from "../../../types/consent";
import "./AlwaysAllowSettings.css";

/**
 * The agent's actions that ask its owner first (posting, sending email, an MCP tool that changes things), each with
 * "Always allow": on, the agent does it without a card, in chat and when it runs on a schedule, until switched off.
 * `keyPrefix` shows only skills' actions ("skill:") or MCP tools ("mcp:").
 */
export function AlwaysAllowSettings({ agentId, keyPrefix }: { agentId: string; keyPrefix: "skill:" | "mcp:" }) {
  const [actions, setActions] = useState<ConsentAction[] | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    consentApiService
      .listStanding(agentId)
      .then((listed) => !cancelled && setActions(listed.filter((action) => action.key.startsWith(keyPrefix))))
      .catch((err) => console.error("Failed to load the agent's approvals:", err));
    return () => {
      cancelled = true;
    };
  }, [agentId, keyPrefix]);

  if (!actions?.length) return null;

  const toggle = async (action: ConsentAction, always: boolean) => {
    setSaving(action.key);
    setError(null);
    try {
      if (always) await consentApiService.alwaysAllow(agentId, action.key);
      else await consentApiService.askEveryTime(agentId, action.key);
      setActions((current) => current?.map((item) => (item.key === action.key ? { ...item, always_allowed: always } : item)) ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "That didn't save. Try again.");
    } finally {
      setSaving(null);
    }
  };

  return (
    <section className="always-allow" aria-labelledby="always-allow-title">
      <header className="always-allow__header">
        <ShieldCheck className="h-4 w-4" aria-hidden />
        <div>
          <h3 id="always-allow-title" className="always-allow__title">Asks you first</h3>
          <p className="always-allow__description">
            These act for you, so the agent shows you each one to approve. Always allow one to let it go ahead without
            asking, including when the agent runs on a schedule.
          </p>
        </div>
      </header>
      {error && <p className="always-allow__error">{error}</p>}
      <ul className="always-allow__list">
        {actions.map((action) => (
          <li key={action.key} className="always-allow__row">
            <div className="always-allow__text">
              <strong>{action.title}</strong>
              <small>
                {action.source}
                {action.warning ? ` · ${action.warning}` : ""}
              </small>
            </div>
            <label className="always-allow__toggle">
              <span>{action.always_allowed ? "Always allow" : "Ask every time"}</span>
              <Switch
                checked={action.always_allowed}
                disabled={saving === action.key}
                aria-label={`Always allow ${action.title}`}
                onCheckedChange={(checked) => void toggle(action, checked)}
              />
            </label>
          </li>
        ))}
      </ul>
    </section>
  );
}
