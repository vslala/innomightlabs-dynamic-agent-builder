import type { FormValue } from "../../../types/form";
import type { InstalledSkill } from "../../../types/skills";

/** The install form's own fields. The API serves them first in a skill's install schema (`with_identity`). */
export const INSTALL_TITLE_FIELD = "install_title";
export const INSTALL_DESCRIPTION_FIELD = "install_description";

export interface InstallIdentity {
  title?: string;
  description?: string;
}

/** Separates what the agent reads about an install (title, description) from the skill's own settings. */
export function splitInstallIdentity(data: Record<string, FormValue>): {
  identity: InstallIdentity;
  settings: Record<string, FormValue>;
} {
  const { [INSTALL_TITLE_FIELD]: title, [INSTALL_DESCRIPTION_FIELD]: description, ...settings } = data;
  const identity: InstallIdentity = {};
  if (typeof title === "string" && title.trim()) identity.title = title.trim();
  // An emptied description is sent as "" so the API clears it; a missing one leaves it alone
  if (typeof description === "string") identity.description = description.trim();
  return { identity, settings };
}

/** The form's starting values when configuring an installed skill: its settings plus its title and description. */
export function installedSkillValues(skill: InstalledSkill): Record<string, FormValue> {
  return {
    [INSTALL_TITLE_FIELD]: skill.name,
    [INSTALL_DESCRIPTION_FIELD]: skill.description,
    ...skill.config,
  };
}
