import { describe, expect, it } from "vitest";

import type { InstalledSkill } from "../../../types/skills";
import { installedSkillValues, splitInstallIdentity } from "./skillInstallIdentity";

describe("splitInstallIdentity", () => {
  it("separates the title and description from the skill's settings", () => {
    const { identity, settings } = splitInstallIdentity({
      install_title: "  Company blog ",
      install_description: "Search our blog.",
      site_url: "https://example.com",
    });

    expect(identity).toEqual({ title: "Company blog", description: "Search our blog." });
    expect(settings).toEqual({ site_url: "https://example.com" });
  });

  it("sends an emptied description so the API clears it, and leaves out a blank title", () => {
    const { identity } = splitInstallIdentity({ install_title: "   ", install_description: "  " });

    expect(identity).toEqual({ description: "" });
  });

  it("sends nothing when the form has neither field", () => {
    expect(splitInstallIdentity({ site_url: "https://example.com" }).identity).toEqual({});
  });
});

describe("installedSkillValues", () => {
  it("starts the form with the install's title, description and settings", () => {
    const skill = {
      name: "Company blog",
      description: "Search our blog.",
      config: { site_url: "https://example.com" },
    } as unknown as InstalledSkill;

    expect(installedSkillValues(skill)).toEqual({
      install_title: "Company blog",
      install_description: "Search our blog.",
      site_url: "https://example.com",
    });
  });
});
