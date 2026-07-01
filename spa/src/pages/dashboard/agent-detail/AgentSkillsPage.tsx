import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, Plus, Power, PowerOff, Search, Wrench } from "lucide-react";

import { SchemaForm } from "../../../components/forms";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../../../components/ui/dialog";
import { connectorApiService } from "../../../services/connectors";
import { skillApiService } from "../../../services/skills";
import type { FormValue, FormSchema } from "../../../types/form";
import type { InstalledSkill, SkillCatalogItem, SkillConnectorStatus } from "../../../types/skills";
import { useAgentDetailContext } from "./types";

function getMissingRequiredConnectors(skill: SkillCatalogItem): SkillConnectorStatus[] {
  return (skill.connectors ?? []).filter((connector) => connector.required && !connector.connected);
}

function hasConnectorMetadata(skill: SkillCatalogItem): boolean {
  return (skill.connectors ?? []).length > 0;
}

function canInstallSkill(skill: SkillCatalogItem): boolean {
  if (hasConnectorMetadata(skill)) {
    return getMissingRequiredConnectors(skill).length === 0;
  }
  return !skill.requires_oauth || skill.oauth_connected === true;
}

const ALL_SKILLS_CATEGORY = "__all__";

function getSkillCategory(skill: SkillCatalogItem): string {
  return skill.namespace.split(".")[0]?.trim() || "other";
}

function prettifyCategory(category: string): string {
  return category
    .split(/[-_]/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function AgentSkillsPage() {
  const { agent } = useAgentDetailContext();
  const [installedSkills, setInstalledSkills] = useState<InstalledSkill[]>([]);
  const [availableSkills, setAvailableSkills] = useState<SkillCatalogItem[]>([]);
  const [loadingSkills, setLoadingSkills] = useState(false);
  const [isSkillDialogOpen, setIsSkillDialogOpen] = useState(false);
  const [selectedSkill, setSelectedSkill] = useState<SkillCatalogItem | null>(null);
  const [selectedSkillSchema, setSelectedSkillSchema] = useState<FormSchema | null>(null);
  const [selectedCategory, setSelectedCategory] = useState(ALL_SKILLS_CATEGORY);
  const [skillSearch, setSkillSearch] = useState("");
  const [installSkillError, setInstallSkillError] = useState<string | null>(null);
  const [installingSkill, setInstallingSkill] = useState(false);
  const [connectingSkillId, setConnectingSkillId] = useState<string | null>(null);
  const [updatingSkillId, setUpdatingSkillId] = useState<string | null>(null);
  const [uninstallingSkillId, setUninstallingSkillId] = useState<string | null>(null);
  const handledSkillOAuthCallbackRef = useRef(false);

  const loadInstalledSkills = async (): Promise<InstalledSkill[]> => {
    setLoadingSkills(true);
    try {
      const skills = await skillApiService.listInstalledSkills(agent.agent_id);
      setInstalledSkills(skills);
      return skills;
    } catch (err) {
      console.error("Error loading installed skills:", err);
      return [];
    } finally {
      setLoadingSkills(false);
    }
  };

  const refreshAvailableSkills = async (): Promise<SkillCatalogItem[]> => {
    const allSkills = await skillApiService.listSkills();
    setAvailableSkills(allSkills);
    return allSkills;
  };

  const installedSkillIds = useMemo(
    () => new Set(installedSkills.map((skill) => skill.skill_id)),
    [installedSkills]
  );

  const skillCategories = useMemo(() => {
    const counts = new Map<string, number>();
    availableSkills.forEach((skill) => {
      const category = getSkillCategory(skill);
      counts.set(category, (counts.get(category) ?? 0) + 1);
    });

    const categories = Array.from(counts.entries())
      .sort(([left], [right]) => prettifyCategory(left).localeCompare(prettifyCategory(right)))
      .map(([category, count]) => ({
        id: category,
        label: prettifyCategory(category),
        count,
      }));

    return [
      {
        id: ALL_SKILLS_CATEGORY,
        label: "All Skills",
        count: availableSkills.length,
      },
      ...categories,
    ];
  }, [availableSkills]);

  const visibleSkills = useMemo(() => {
    const normalizedSearch = skillSearch.trim().toLowerCase();
    return availableSkills
      .filter((skill) => selectedCategory === ALL_SKILLS_CATEGORY || getSkillCategory(skill) === selectedCategory)
      .filter((skill) => {
        if (!normalizedSearch) return true;
        return [skill.name, skill.description, skill.namespace]
          .some((value) => value.toLowerCase().includes(normalizedSearch));
      })
      .sort((left, right) => left.name.localeCompare(right.name));
  }, [availableSkills, selectedCategory, skillSearch]);

  useEffect(() => {
    loadInstalledSkills().then(() => {
      void refreshAvailableSkills();
    });
  }, [agent.agent_id]);

  useEffect(() => {
    async function handleSkillOAuthCallback() {
      if (handledSkillOAuthCallbackRef.current) return;

      const params = new URLSearchParams(window.location.search);
      const status = params.get("skill_oauth");
      const callbackAgentId = params.get("agent_id");
      const callbackSkillId = params.get("skill_id");

      if (!status || !callbackSkillId) {
        return;
      }
      if (callbackAgentId && callbackAgentId !== agent.agent_id) {
        return;
      }

      handledSkillOAuthCallbackRef.current = true;

      try {
        const currentInstalled = await loadInstalledSkills();
        const available = await refreshAvailableSkills();
        const callbackSkill = available.find((item) => item.skill_id === callbackSkillId) ?? null;

        if (status !== "success") {
          setInstallSkillError("Skill connection failed");
          setIsSkillDialogOpen(true);
          setSelectedSkill(callbackSkill);
          setSelectedSkillSchema(null);
          return;
        }

        const alreadyInstalled = currentInstalled.some((skill) => skill.skill_id === callbackSkillId);
        if (!alreadyInstalled) {
          await skillApiService.installSkill(agent.agent_id, callbackSkillId, { config: {} });
          await loadInstalledSkills();
          await refreshAvailableSkills();
        }

        setIsSkillDialogOpen(false);
        setSelectedSkill(null);
        setSelectedSkillSchema(null);
      } catch (err: unknown) {
        const available = await refreshAvailableSkills().catch(() => []);
        setSelectedSkill(available.find((item) => item.skill_id === callbackSkillId) ?? null);
        setSelectedSkillSchema(null);
        setInstallSkillError(err instanceof Error ? err.message : "Failed to install connected skill");
        setIsSkillDialogOpen(true);
      } finally {
        params.delete("skill_oauth");
        params.delete("google_drive_oauth");
        params.delete("google_mail_oauth");
        params.delete("agent_id");
        params.delete("skill_id");
        params.delete("reason");
        const nextQuery = params.toString();
        const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ""}`;
        window.history.replaceState({}, "", nextUrl);
      }
    }

    void handleSkillOAuthCallback();
  }, [agent.agent_id]);

  const openSkillDialog = async () => {
    setInstallSkillError(null);
    setSelectedSkill(null);
    setSelectedSkillSchema(null);
    setSelectedCategory(ALL_SKILLS_CATEGORY);
    setSkillSearch("");
    try {
      await refreshAvailableSkills();
      setIsSkillDialogOpen(true);
    } catch (err) {
      console.error("Error loading skill catalog:", err);
      setInstallSkillError("Failed to load skill catalog");
    }
  };

  const selectSkillForInstall = async (skill: SkillCatalogItem) => {
    if (installedSkillIds.has(skill.skill_id)) return;
    setInstallSkillError(null);
    setSelectedSkill(skill);
    setSelectedSkillSchema(null);
    try {
      if (!canInstallSkill(skill) || !skill.has_form) {
        setSelectedSkillSchema(null);
        return;
      }
      const schema = await skillApiService.getSkillInstallSchema(skill.skill_id);
      setSelectedSkillSchema(schema);
    } catch (err: unknown) {
      setInstallSkillError(err instanceof Error ? err.message : "Failed to load skill form");
      setSelectedSkillSchema(null);
    }
  };

  const handleInstallSkill = async (data: Record<string, FormValue>) => {
    if (!selectedSkill) return;
    setInstallingSkill(true);
    setInstallSkillError(null);
    try {
      const payload: Record<string, string> = {};
      for (const [key, value] of Object.entries(data)) {
        if (typeof value === "string") payload[key] = value;
      }
      await skillApiService.installSkill(agent.agent_id, selectedSkill.skill_id, { config: payload });
      setIsSkillDialogOpen(false);
      setSelectedSkill(null);
      setSelectedSkillSchema(null);
      await loadInstalledSkills();
      await refreshAvailableSkills();
    } catch (err: unknown) {
      setInstallSkillError(err instanceof Error ? err.message : "Failed to install skill");
    } finally {
      setInstallingSkill(false);
    }
  };

  const handleConnectSkillOAuth = async () => {
    if (!selectedSkill) return;
    const missingConnector = getMissingRequiredConnectors(selectedSkill)[0];
    if (missingConnector) {
      if (!missingConnector.connect_path) {
        setInstallSkillError(`No connection path is available for ${missingConnector.provider_name}`);
        return;
      }
      setConnectingSkillId(selectedSkill.skill_id);
      setInstallSkillError(null);
      try {
        const returnTo = `${window.location.origin}/dashboard/agents/${agent.agent_id}/skills`;
        const response = await connectorApiService.startConnector(missingConnector.connect_path, {
          return_to: returnTo,
        });
        window.location.href = response.authorize_url;
      } catch (err: unknown) {
        setInstallSkillError(err instanceof Error ? err.message : `Failed to connect ${missingConnector.provider_name}`);
        setConnectingSkillId(null);
      }
      return;
    }

    if (!selectedSkill.oauth_start_path) {
      setInstallSkillError(`No OAuth start path is available for ${selectedSkill.oauth_provider_name ?? selectedSkill.name}`);
      return;
    }
    setConnectingSkillId(selectedSkill.skill_id);
    setInstallSkillError(null);
    try {
      const returnTo = `${window.location.origin}/dashboard/agents/${agent.agent_id}/skills`;
      const response = await skillApiService.startSkillOAuth(selectedSkill.oauth_start_path, {
        agent_id: agent.agent_id,
        skill_id: selectedSkill.skill_id,
        return_to: returnTo,
      });
      window.location.href = response.authorize_url;
    } catch (err: unknown) {
      setInstallSkillError(err instanceof Error ? err.message : `Failed to connect ${selectedSkill.oauth_provider_name ?? selectedSkill.name}`);
      setConnectingSkillId(null);
    }
  };

  const handleToggleSkill = async (skill: InstalledSkill) => {
    const installedSkillId = skill.installed_skill_id ?? skill.skill_id;
    setUpdatingSkillId(installedSkillId);
    try {
      const updated = await skillApiService.updateInstalledSkill(agent.agent_id, installedSkillId, {
        enabled: !skill.enabled,
      });
      setInstalledSkills((prev) =>
        prev.map((item) => ((item.installed_skill_id ?? item.skill_id) === updated.installed_skill_id ? updated : item))
      );
    } catch (err) {
      console.error("Error toggling skill:", err);
    } finally {
      setUpdatingSkillId(null);
    }
  };

  const handleUpdateSkillConfig = async (skill: InstalledSkill, data: Record<string, FormValue>) => {
    const installedSkillId = skill.installed_skill_id ?? skill.skill_id;
    setUpdatingSkillId(installedSkillId);
    try {
      const payload: Record<string, string> = {};
      for (const [key, value] of Object.entries(data)) {
        if (typeof value === "string") payload[key] = value;
      }
      const updated = await skillApiService.updateInstalledSkill(agent.agent_id, installedSkillId, {
        config: payload,
      });
      setInstalledSkills((prev) =>
        prev.map((item) => ((item.installed_skill_id ?? item.skill_id) === updated.installed_skill_id ? updated : item))
      );
    } catch (err) {
      console.error("Error updating skill config:", err);
    } finally {
      setUpdatingSkillId(null);
    }
  };

  const handleUninstallSkill = async (skill: InstalledSkill) => {
    const disconnectOAuth = skill.requires_oauth && skill.oauth_provider_name
      ? window.confirm(`Uninstall ${skill.name}. Press OK to also disconnect ${skill.oauth_provider_name} for your account, or Cancel to uninstall only and keep the OAuth connection.`)
      : false;

    const installedSkillId = skill.installed_skill_id ?? skill.skill_id;
    setUninstallingSkillId(installedSkillId);
    try {
      await skillApiService.uninstallSkill(agent.agent_id, installedSkillId, { disconnectOAuth });
      setInstalledSkills((prev) => prev.filter((item) => (item.installed_skill_id ?? item.skill_id) !== installedSkillId));
      await refreshAvailableSkills();
    } catch (err) {
      console.error("Error uninstalling skill:", err);
    } finally {
      setUninstallingSkillId(null);
    }
  };

  return (
    <>
      <Card>
        <CardHeader>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Wrench style={{ height: "1.25rem", width: "1.25rem", color: "var(--gradient-start)" }} />
              <CardTitle className="text-lg">Skills</CardTitle>
            </div>
            <Button size="action" onClick={openSkillDialog}>
              <Plus style={{ height: "1rem", width: "1rem" }} />
              Add Skill
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
            Install reusable skills to give this agent task-specific capabilities with secure configuration.
          </p>
          {loadingSkills ? (
            <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
              <div style={{ height: "2rem", width: "2rem", animation: "spin 1s linear infinite", borderRadius: "50%", border: "2px solid var(--gradient-start)", borderTopColor: "transparent" }} />
            </div>
          ) : installedSkills.length === 0 ? (
            <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>
              <Wrench style={{ height: "3rem", width: "3rem", margin: "0 auto 1rem", opacity: 0.5 }} />
              <p>No skills installed</p>
              <p style={{ fontSize: "0.875rem" }}>Install a skill to enable specialized actions.</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {installedSkills.map((skill) => {
                const installedSkillId = skill.installed_skill_id ?? skill.skill_id;
                return (
                <div key={installedSkillId} style={{ border: "1px solid var(--border-subtle)", borderRadius: "0.75rem", padding: "1rem" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem" }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
                        <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{skill.name}</span>
                        <span style={{ fontSize: "0.75rem", color: skill.enabled ? "#10b981" : "var(--text-muted)", backgroundColor: skill.enabled ? "rgba(16, 185, 129, 0.1)" : "var(--bg-tertiary)", padding: "0.125rem 0.5rem", borderRadius: "0.25rem" }}>
                          {skill.enabled ? "Enabled" : "Disabled"}
                        </span>
                      </div>
                      <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>{skill.description}</p>
                      {Object.keys(skill.config).length > 0 && (
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                          {Object.entries(skill.config).map(([key, value]) => (
                            <div key={key}>
                              <span style={{ color: "var(--text-primary)" }}>{key}:</span> {value}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    <div style={{ display: "flex", width: "8.75rem", flexShrink: 0, flexDirection: "column", gap: "0.625rem", alignItems: "stretch" }}>
                      <Button variant="outline" size="action" onClick={() => handleToggleSkill(skill)} disabled={updatingSkillId === installedSkillId} className="w-full">
                        {skill.enabled ? (
                          <>
                            <PowerOff className="h-4 w-4" />
                            Disable
                          </>
                        ) : (
                          <>
                            <Power className="h-4 w-4" />
                            Enable
                          </>
                        )}
                      </Button>
                      <Button variant="destructive" size="action" onClick={() => handleUninstallSkill(skill)} disabled={uninstallingSkillId === installedSkillId} className="w-full">
                        {uninstallingSkillId === installedSkillId ? "Removing..." : "Uninstall"}
                      </Button>
                      {Object.keys(skill.config).length > 0 && (
                        <Button
                          variant="outline"
                          size="action"
                          onClick={() => handleUpdateSkillConfig(skill, skill.config)}
                          disabled={updatingSkillId === installedSkillId}
                          className="w-full"
                        >
                          {updatingSkillId === installedSkillId ? "Saving..." : "Refresh Config"}
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={isSkillDialogOpen} onOpenChange={setIsSkillDialogOpen}>
        <DialogContent style={{ width: "min(92vw, 88rem)", maxWidth: "88rem" }}>
          <DialogHeader>
            <DialogTitle>Add Skill</DialogTitle>
            <DialogDescription>
              Install a skill and configure it for this agent.
            </DialogDescription>
          </DialogHeader>
          <div style={{ display: "grid", gridTemplateColumns: "13rem minmax(0, 1fr) 24rem", gap: "1rem", minHeight: "40rem" }}>
            <aside style={{ borderRight: "1px solid var(--border-subtle)", paddingRight: "0.75rem" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                {skillCategories.map((category) => {
                  const selected = selectedCategory === category.id;
                  return (
                    <Button
                      key={category.id}
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setSelectedCategory(category.id);
                        setSelectedSkill(null);
                        setSelectedSkillSchema(null);
                        setInstallSkillError(null);
                      }}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: "0.5rem",
                        width: "100%",
                        minWidth: 0,
                        border: "none",
                        borderRadius: "0.5rem",
                        background: selected ? "rgba(99, 102, 241, 0.12)" : "transparent",
                        color: selected ? "var(--text-primary)" : "var(--text-muted)",
                        height: "auto",
                        padding: "0.55rem 0.65rem",
                        textAlign: "left",
                        whiteSpace: "normal",
                        fontSize: "0.875rem",
                        fontWeight: selected ? 600 : 500,
                      }}
                    >
                      <span style={{ minWidth: 0, overflowWrap: "anywhere" }}>{category.label}</span>
                      <span style={{ fontSize: "0.75rem", color: selected ? "var(--gradient-start)" : "var(--text-muted)" }}>
                        {category.count}
                      </span>
                    </Button>
                  );
                })}
              </div>
            </aside>

            <section style={{ display: "flex", flexDirection: "column", gap: "0.875rem", minWidth: 0 }}>
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "0.5rem",
                  padding: "0.625rem 0.75rem",
                  background: "var(--bg-secondary)",
                }}
              >
                <Search className="h-4 w-4" style={{ color: "var(--text-muted)" }} />
                <input
                  value={skillSearch}
                  onChange={(event) => setSkillSearch(event.target.value)}
                  placeholder="Search for a skill you want to use"
                  style={{
                    width: "100%",
                    border: "none",
                    outline: "none",
                    background: "transparent",
                    color: "var(--text-primary)",
                    fontSize: "0.875rem",
                  }}
                />
              </label>

              <div style={{ maxHeight: "36rem", overflowY: "auto", paddingRight: "0.25rem" }}>
                {availableSkills.length === 0 ? (
                  <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>No skills available.</p>
                ) : visibleSkills.length === 0 ? (
                  <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>No skills match this category or search.</p>
                ) : (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(13rem, 1fr))", gap: "0.75rem" }}>
                    {visibleSkills.map((skill) => {
                      const installed = installedSkillIds.has(skill.skill_id);
                      const selected = selectedSkill?.skill_id === skill.skill_id;
                      return (
                        <Button
                          key={skill.skill_id}
                          type="button"
                          variant="ghost"
                          disabled={installed}
                          onClick={() => void selectSkillForInstall(skill)}
                          style={{
                            position: "relative",
                            display: "block",
                            minHeight: "8.25rem",
                            minWidth: 0,
                            height: "auto",
                            border: selected ? "2px solid var(--gradient-start)" : "1px solid var(--border-subtle)",
                            borderRadius: "0.5rem",
                            background: installed ? "rgba(255, 255, 255, 0.03)" : "var(--bg-secondary)",
                            color: "inherit",
                            padding: "0.875rem",
                            textAlign: "left",
                            whiteSpace: "normal",
                            cursor: installed ? "not-allowed" : "pointer",
                            opacity: installed ? 0.72 : 1,
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "0.75rem", marginBottom: "0.75rem" }}>
                            <div
                              style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                width: "2rem",
                                height: "2rem",
                                borderRadius: "0.5rem",
                                background: "rgba(99, 102, 241, 0.14)",
                                color: "var(--gradient-start)",
                                fontSize: "0.8125rem",
                                fontWeight: 700,
                              }}
                            >
                              {skill.name.charAt(0).toUpperCase()}
                            </div>
                            {installed && (
                              <span
                                style={{
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: "0.25rem",
                                  borderRadius: "999px",
                                  background: "rgba(16, 185, 129, 0.12)",
                                  color: "#34d399",
                                  padding: "0.2rem 0.45rem",
                                  fontSize: "0.6875rem",
                                  fontWeight: 700,
                                }}
                              >
                                <CheckCircle2 className="h-3 w-3" />
                                Installed
                              </span>
                            )}
                          </div>
                          <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.35rem", lineHeight: 1.3, overflowWrap: "anywhere" }}>
                            {skill.name}
                          </div>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", lineHeight: 1.4, overflowWrap: "anywhere" }}>
                            {skill.description}
                          </div>
                          <div style={{ marginTop: "0.75rem", fontSize: "0.6875rem", color: "var(--text-muted)", overflowWrap: "anywhere" }}>
                            {skill.namespace}
                          </div>
                        </Button>
                      );
                    })}
                  </div>
                )}
              </div>
            </section>

            <section style={{ borderLeft: "1px solid var(--border-subtle)", paddingLeft: "1rem", minWidth: 0 }}>
              {!selectedSkill ? (
                <div style={{ border: "1px dashed var(--border-subtle)", borderRadius: "0.75rem", padding: "1rem", color: "var(--text-muted)" }}>
                  <p style={{ fontSize: "0.875rem", marginBottom: "0.25rem", color: "var(--text-primary)", fontWeight: 600 }}>
                    Select a skill
                  </p>
                  <p style={{ fontSize: "0.8125rem", lineHeight: 1.5 }}>
                    Choose a skill from the catalog to configure and install it for this agent.
                  </p>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  <div>
                    <p style={{ fontWeight: 600, color: "var(--text-primary)" }}>{selectedSkill.name}</p>
                    <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>{selectedSkill.description}</p>
                    {hasConnectorMetadata(selectedSkill) ? (
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem", marginTop: "0.375rem" }}>
                        {selectedSkill.connectors.map((connector) => (
                          <p key={connector.connector_id} style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            {connector.connected
                              ? `Connected via ${connector.provider_name}`
                              : `Requires ${connector.provider_name} connector before install`}
                          </p>
                        ))}
                      </div>
                    ) : selectedSkill.requires_oauth && (
                      <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.375rem" }}>
                        {selectedSkill.oauth_connected
                          ? `Connected via ${selectedSkill.oauth_provider_name}`
                          : `Requires ${selectedSkill.oauth_provider_name} connection before install`}
                      </p>
                    )}
                  </div>
                  {installSkillError && (
                    <div style={{ padding: "0.75rem", borderRadius: "0.5rem", backgroundColor: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.2)", color: "#f87171", fontSize: "0.875rem" }}>
                      {installSkillError}
                    </div>
                  )}
                  {!canInstallSkill(selectedSkill) && (
                    <Button onClick={handleConnectSkillOAuth} disabled={connectingSkillId === selectedSkill.skill_id}>
                      {connectingSkillId === selectedSkill.skill_id
                        ? "Connecting..."
                        : `Connect ${getMissingRequiredConnectors(selectedSkill)[0]?.provider_name ?? selectedSkill.oauth_provider_name ?? selectedSkill.name}`}
                    </Button>
                  )}
                  {selectedSkillSchema && (
                    <SchemaForm
                      schema={selectedSkillSchema}
                      onSubmit={handleInstallSkill}
                      submitLabel={installingSkill ? "Installing..." : "Install Skill"}
                      isLoading={installingSkill}
                    />
                  )}
                  {!selectedSkillSchema && canInstallSkill(selectedSkill) && (
                    <Button onClick={() => void handleInstallSkill({})} disabled={installingSkill}>
                      {installingSkill ? "Installing..." : "Install Skill"}
                    </Button>
                  )}
                </div>
              )}
            </section>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
