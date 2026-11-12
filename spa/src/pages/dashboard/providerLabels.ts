/** The words the Settings page uses for a provider: its title, what its row offers, and the removal question. */

// Provider ids are stored on agents, so the two ways into OpenAI get readable titles here.
const PROVIDER_TITLES: Record<string, string> = {
  OpenAI: "OpenAI (OAuth)",
  OpenAIAPI: "OpenAI (API key)",
};

export const providerTitle = (providerName: string): string => PROVIDER_TITLES[providerName] ?? providerName;

/** OpenAI is signed into rather than given a key, so its credentials are connected and disconnected. */
const isOAuth = (providerName: string): boolean => providerName === "OpenAI";

/** What a provider's row offers: how to (re)configure it, and how to take it back to not set up. */
export function providerActions(providerName: string, isConfigured: boolean): { configure: string; remove: string | null } {
  if (isOAuth(providerName)) {
    return { configure: isConfigured ? "Reconnect" : "Connect", remove: isConfigured ? "Disconnect" : null };
  }
  return { configure: isConfigured ? "Update" : "Configure", remove: isConfigured ? "Remove" : null };
}

export const providerStatus = (providerName: string, isConfigured: boolean): string => {
  if (isOAuth(providerName)) return isConfigured ? "Connected via OAuth" : "Not connected";
  return isConfigured ? "Configured" : "Not configured";
};

/** The question asked before a provider's saved credentials are deleted. */
export function removalPrompt(providerName: string): { title: string; description: string; confirm: string; busy: string } {
  const title = providerTitle(providerName);
  const { remove } = providerActions(providerName, true);
  const verb = remove ?? "Remove";
  return {
    title: `${verb} ${title}?`,
    description: `This deletes the account's saved ${title} credentials. Agents that use ${title} stop working until it is set up again.`,
    confirm: verb,
    busy: verb === "Remove" ? "Removing..." : "Disconnecting...",
  };
}
