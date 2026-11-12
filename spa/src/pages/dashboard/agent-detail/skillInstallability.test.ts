import { describe, expect, it } from "vitest";
import type { SkillCatalogItem } from "../../../types/skills";
import { canInstallSkill, getUnmetRequirements } from "./skillInstallability";

const skill = (fields: Partial<SkillCatalogItem> = {}): SkillCatalogItem =>
  ({ requires_oauth: false, oauth_connected: null, connectors: [], requirements: [], ...fields }) as SkillCatalogItem;

const requirement = (met: boolean) => ({
  name: "image_generation",
  needs: "image generation set up first",
  setup_path: "/dashboard/settings",
  met,
});

describe("canInstallSkill", () => {
  it("is blocked until what the skill requires is set up", () => {
    expect(canInstallSkill(skill({ requirements: [requirement(false)] }))).toBe(false);
    expect(canInstallSkill(skill({ requirements: [requirement(true)] }))).toBe(true);
  });

  it("still waits for a connector or sign-in, whatever else is met", () => {
    const connector = { connector_id: "c", provider_name: "Google", required: true, connected: false, connect_path: null };
    expect(canInstallSkill(skill({ requirements: [requirement(true)], connectors: [connector] }))).toBe(false);
    expect(canInstallSkill(skill({ requires_oauth: true, oauth_connected: false }))).toBe(false);
    expect(canInstallSkill(skill())).toBe(true);
  });

  it("copes with a catalog that predates requirements", () => {
    expect(canInstallSkill(skill({ requirements: undefined }))).toBe(true);
    expect(getUnmetRequirements(skill({ requirements: undefined }))).toEqual([]);
  });
});
