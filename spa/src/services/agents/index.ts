import type { IAgentService } from "./IAgentService";
import { LocalStorageAgentService } from "./LocalStorageAgentService";

export type { IAgentService };
export * from "./IAgentService";

let agentServiceInstance: IAgentService | null = null;

export function getAgentService(): IAgentService {
  if (!agentServiceInstance) {
    // Switch implementation based on environment variable
    const backend = import.meta.env.VITE_AGENT_BACKEND;

    if (backend === "api") {
      // TODO: Implement ApiAgentService when backend is ready
      // agentServiceInstance = new ApiAgentService();
      console.warn("API backend not implemented yet, falling back to localStorage");
      agentServiceInstance = new LocalStorageAgentService();
    } else {
      agentServiceInstance = new LocalStorageAgentService();
    }
  }

  return agentServiceInstance;
}

// Reset service instance (useful for testing)
export function resetAgentService(): void {
  agentServiceInstance = null;
}
