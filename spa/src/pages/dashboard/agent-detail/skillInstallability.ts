import type { SkillCatalogItem, SkillConnectorStatus, SkillRequirementStatus } from "../../../types/skills";

export function getMissingRequiredConnectors(skill: SkillCatalogItem): SkillConnectorStatus[] {
  return (skill.connectors ?? []).filter((connector) => connector.required && !connector.connected);
}

export function hasConnectorMetadata(skill: SkillCatalogItem): boolean {
  return (skill.connectors ?? []).length > 0;
}

/** What the account has to set up before the skill can be installed (its manifest's `requires`). */
export function getUnmetRequirements(skill: SkillCatalogItem): SkillRequirementStatus[] {
  return (skill.requirements ?? []).filter((requirement) => !requirement.met);
}

export function canInstallSkill(skill: SkillCatalogItem): boolean {
  if (getUnmetRequirements(skill).length > 0) return false;
  if (hasConnectorMetadata(skill)) {
    return getMissingRequiredConnectors(skill).length === 0;
  }
  return !skill.requires_oauth || skill.oauth_connected === true;
}
