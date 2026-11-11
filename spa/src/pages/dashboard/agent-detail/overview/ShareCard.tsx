/**
 * The two ways an agent leaves its owner's hands: Agent2Agent discovery, and a marketplace template.
 *
 * A2A's endpoints and public card are only worth showing once discovery is on, and then they sit behind one
 * "Show" so the card stays short. Until there is an active API key the switch is off and the card says why.
 */

import { useState } from "react";
import { ChevronDown, ChevronUp, Key, ShoppingBag } from "lucide-react";

import { Button, CopyButton, LinkButton, Switch } from "../../../../components/ui";
import type { Agent2AgentSharingResponse, AgentResponse } from "../../../../services/agents/AgentApiService";
import { OverviewCard } from "./OverviewCard";
import type { A2ASharing } from "./useOverviewData";

export function ShareCard({
  agent,
  a2a,
  apiKeysPath,
  onPublish,
}: {
  agent: AgentResponse;
  a2a: A2ASharing;
  apiKeysPath: string;
  onPublish: () => void;
}) {
  const sharing = a2a.sharing.state === "ready" ? a2a.sharing.value : null;
  const enabled = Boolean(sharing?.enabled);
  // Turning discovery off never needs a key; turning it on does
  const canToggle = sharing !== null && !a2a.updating && (enabled || sharing.has_active_api_key);

  return (
    <OverviewCard id="agent-share" title="Share">
      <div className="agent-overview-share-row">
        <span>
          <strong id="agent-a2a-label">Agent2Agent discovery</strong>
          <small>{enabled ? "Other agents can find and message it" : "Let other agents find and message it"}</small>
        </span>
        <Switch
          checked={enabled}
          disabled={!canToggle}
          aria-labelledby="agent-a2a-label"
          onCheckedChange={(next) => void a2a.setEnabled(next)}
        />
      </div>

      {a2a.sharing.state === "failed" && (
        <p className="agent-overview-error" role="alert">
          Failed to load Agent2Agent settings.
        </p>
      )}
      {a2a.error && (
        <p className="agent-overview-error" role="alert">
          {a2a.error}
        </p>
      )}
      {sharing && !sharing.has_active_api_key && !enabled && (
        <div className="agent-overview-blocker">
          <Key aria-hidden="true" />
          <span>Needs an active API key.</span>
          <LinkButton to={apiKeysPath} variant="link" size="sm">
            Create key
          </LinkButton>
        </div>
      )}
      {sharing && enabled && <Endpoints agent={agent} sharing={sharing} />}

      <hr className="agent-overview-divider" />

      <div className="agent-overview-share-row">
        <span>
          <strong>Marketplace template</strong>
          <small>Instructions and chosen skills, never secrets</small>
        </span>
        <Button type="button" variant="outline" size="sm" onClick={onPublish}>
          <ShoppingBag />
          Publish
        </Button>
      </div>
    </OverviewCard>
  );
}

function Endpoints({ agent, sharing }: { agent: AgentResponse; sharing: Agent2AgentSharingResponse }) {
  const [open, setOpen] = useState(false);
  const registryUrl = registryUrlOf(sharing);
  const urls = [
    ...(registryUrl ? [{ label: "Registry URL", value: registryUrl }] : []),
    { label: "Agent Card URL", value: sharing.agent_card_url },
    { label: "Agent Service URL", value: sharing.service_url },
  ];

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="agent-overview-disclosure"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? <ChevronUp /> : <ChevronDown />}
        {open ? "Hide" : "Show"} endpoints and public card
      </Button>
      {open && (
        <div className="agent-overview-endpoints">
          {urls.map((url) => (
            <div key={url.label} className="agent-overview-endpoint">
              <span>{url.label}</span>
              <div>
                <code title={url.value}>{url.value}</code>
                <CopyButton value={url.value} label={`Copy ${url.label}`} />
              </div>
            </div>
          ))}
          <div className="agent-overview-public-card">
            <span>What other agents see</span>
            <strong>{agent.agent_name}</strong>
            <p>{agent.agent_description || "InnomightLabs agent enabled for Agent2Agent communication."}</p>
            <div>
              <code>JSONRPC</code>
              <code>chat</code>
              <code>text/plain</code>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/** The public registry lives at the API's origin, which the card and service URLs carry. */
function registryUrlOf(sharing: Agent2AgentSharingResponse): string {
  const source = sharing.service_url || sharing.agent_card_url;
  try {
    return `${new URL(source).origin}/a2a/agents`;
  } catch {
    return "";
  }
}
