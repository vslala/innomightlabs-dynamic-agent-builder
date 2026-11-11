/**
 * What an agent still needs before it is useful and shareable, as one ordered list.
 *
 * This replaces the old status tiles and readiness checklist, which reported the same facts twice. A check names
 * what unblocks it, so the card can say why an action isn't available yet instead of showing a disabled button.
 */

export type SetupAction = "edit" | "api-keys" | "skills" | "knowledge-bases" | "enable-a2a";

export interface SetupCheck {
  key: string;
  label: string;
  /** One line under the label: what's in place, or what's missing. */
  hint: string;
  done: boolean;
  actionLabel: string;
  action: SetupAction;
  /** Why the action can't be taken yet; null when it can. */
  blockedBy: string | null;
}

export interface SetupFacts {
  configured: boolean;
  hasActiveApiKey: boolean;
  a2aEnabled: boolean;
  activeSkills: number;
  linkedKnowledgeBases: number;
}

export function setupChecks(facts: SetupFacts): SetupCheck[] {
  return [
    {
      key: "configured",
      label: "Agent configured",
      hint: facts.configured ? "Name and instructions are set" : "Give it a name and instructions",
      done: facts.configured,
      actionLabel: "Edit agent",
      action: "edit",
      blockedBy: null,
    },
    {
      key: "api-key",
      label: "API key",
      hint: facts.hasActiveApiKey ? "An active key is ready" : "Needed for the widget, the API and A2A",
      done: facts.hasActiveApiKey,
      actionLabel: "Create key",
      action: "api-keys",
      blockedBy: null,
    },
    {
      key: "skills",
      label: "Skills",
      hint: facts.activeSkills ? `${facts.activeSkills} active` : "Let it call tools, APIs and workflows",
      done: facts.activeSkills > 0,
      actionLabel: "Add skills",
      action: "skills",
      blockedBy: null,
    },
    {
      key: "knowledge",
      label: "Knowledge",
      hint: facts.linkedKnowledgeBases
        ? `${facts.linkedKnowledgeBases} linked`
        : "Answers only from its instructions and tools",
      done: facts.linkedKnowledgeBases > 0,
      actionLabel: "Link knowledge",
      action: "knowledge-bases",
      blockedBy: null,
    },
    {
      key: "a2a",
      label: "A2A discovery",
      hint: facts.a2aEnabled ? "Listed in the registry" : "Other agents can't find it yet",
      done: facts.a2aEnabled,
      actionLabel: "Enable",
      action: "enable-a2a",
      blockedBy: facts.hasActiveApiKey ? null : "Needs an API key first",
    },
  ];
}
