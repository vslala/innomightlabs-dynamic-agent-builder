/** The words the Settings page uses for a provider: what its row offers, its status, and the removal question. */

import type { ProviderWithStatus } from "../../services/settings/ProviderSettingsService";

type Provider = Pick<ProviderWithStatus, "title" | "oauth">;

/** A provider signed into rather than given a key is connected and disconnected. */
const isSignedInto = (provider: Provider): boolean => provider.oauth !== null;

/** What a provider's row offers: how to (re)configure it, and how to take it back to not set up. */
export function providerActions(provider: Provider, isConfigured: boolean): { configure: string; remove: string | null } {
  if (isSignedInto(provider)) {
    return { configure: isConfigured ? "Reconnect" : "Connect", remove: isConfigured ? "Disconnect" : null };
  }
  return { configure: isConfigured ? "Update" : "Configure", remove: isConfigured ? "Remove" : null };
}

export const providerStatus = (provider: Provider, isConfigured: boolean): string => {
  if (isSignedInto(provider)) return isConfigured ? "Connected via OAuth" : "Not connected";
  return isConfigured ? "Configured" : "Not configured";
};

/** The question asked before a provider's saved credentials are deleted. */
export function removalPrompt(provider: Provider): { title: string; description: string; confirm: string; busy: string } {
  const { title } = provider;
  const verb = providerActions(provider, true).remove ?? "Remove";
  return {
    title: `${verb} ${title}?`,
    description: `This deletes the account's saved ${title} credentials. Agents that use ${title} stop working until it is set up again.`,
    confirm: verb,
    busy: verb === "Remove" ? "Removing..." : "Disconnecting...",
  };
}
