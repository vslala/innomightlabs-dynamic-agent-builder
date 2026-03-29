import { useEffect, useRef, useState } from "react";
import { Plus, Power, PowerOff, Wrench } from "lucide-react";

import { SchemaForm } from "../../../components/forms";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../../../components/ui/dialog";
import { skillApiService } from "../../../services/skills";
import type { FormValue, FormSchema } from "../../../types/form";
import type { InstalledSkill, SkillCatalogItem } from "../../../types/skills";
import { useAgentDetailContext } from "./types";

export function AgentSkillsPage() {
  const { agent } = useAgentDetailContext();
  const [installedSkills, setInstalledSkills] = useState<InstalledSkill[]>([]);
  const [availableSkills, setAvailableSkills] = useState<SkillCatalogItem[]>([]);
  const [loadingSkills, setLoadingSkills] = useState(false);
  const [isSkillDialogOpen, setIsSkillDialogOpen] = useState(false);
  const [selectedSkill, setSelectedSkill] = useState<SkillCatalogItem | null>(null);
  const [selectedSkillSchema, setSelectedSkillSchema] = useState<FormSchema | null>(null);
  const [installSkillError, setInstallSkillError] = useState<string | null>(null);
  const [installingSkill, setInstallingSkill] = useState(false);
  const [connectingSkillId, setConnectingSkillId] = useState<string | null>(null);
  const [updatingSkillId, setUpdatingSkillId] = useState<string | null>(null);
  const [uninstallingSkillId, setUninstallingSkillId] = useState<string | null>(null);
  const handledGoogleDriveCallbackRef = useRef(false);

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

  const refreshAvailableSkills = async (installedOverride?: InstalledSkill[]): Promise<SkillCatalogItem[]> => {
    const allSkills = await skillApiService.listSkills();
    const installedIds = new Set((installedOverride ?? installedSkills).map((skill) => skill.skill_id));
    const available = allSkills.filter((skill) => !installedIds.has(skill.skill_id));
    setAvailableSkills(available);
    return available;
  };

  useEffect(() => {
    loadInstalledSkills().then((skills) => {
      void refreshAvailableSkills(skills);
    });
  }, [agent.agent_id]);

  useEffect(() => {
    async function handleGoogleDriveOAuthCallback() {
      if (handledGoogleDriveCallbackRef.current) return;

      const params = new URLSearchParams(window.location.search);
      const status = params.get("google_drive_oauth");
      const callbackAgentId = params.get("agent_id");
      const callbackSkillId = params.get("skill_id");

      if (!status || callbackAgentId !== agent.agent_id || callbackSkillId !== "google_drive") {
        return;
      }

      handledGoogleDriveCallbackRef.current = true;

      try {
        const currentInstalled = await loadInstalledSkills();
        const available = await refreshAvailableSkills(currentInstalled);

        if (status !== "success") {
          setInstallSkillError("Google Drive connection failed");
          setIsSkillDialogOpen(true);
          setSelectedSkill(available.find((item) => item.skill_id === "google_drive") ?? null);
          setSelectedSkillSchema(null);
          return;
        }

        const alreadyInstalled = currentInstalled.some((skill) => skill.skill_id === "google_drive");
        if (!alreadyInstalled) {
          await skillApiService.installSkill(agent.agent_id, "google_drive", { config: {} });
          const refreshedInstalled = await loadInstalledSkills();
          await refreshAvailableSkills(refreshedInstalled);
        }

        setIsSkillDialogOpen(false);
        setSelectedSkill(null);
        setSelectedSkillSchema(null);
      } catch (err: unknown) {
        const available = await refreshAvailableSkills().catch(() => []);
        setSelectedSkill(available.find((item) => item.skill_id === "google_drive") ?? null);
        setSelectedSkillSchema(null);
        setInstallSkillError(err instanceof Error ? err.message : "Failed to install Google Drive skill");
        setIsSkillDialogOpen(true);
      } finally {
        params.delete("google_drive_oauth");
        params.delete("agent_id");
        params.delete("skill_id");
        params.delete("reason");
        const nextQuery = params.toString();
        const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ""}`;
        window.history.replaceState({}, "", nextUrl);
      }
    }

    void handleGoogleDriveOAuthCallback();
  }, [agent.agent_id]);

  const openSkillDialog = async () => {
    setInstallSkillError(null);
    setSelectedSkill(null);
    setSelectedSkillSchema(null);
    try {
      await refreshAvailableSkills();
      setIsSkillDialogOpen(true);
    } catch (err) {
      console.error("Error loading skill catalog:", err);
      setInstallSkillError("Failed to load skill catalog");
    }
  };

  const selectSkillForInstall = async (skill: SkillCatalogItem) => {
    setInstallSkillError(null);
    setSelectedSkill(skill);
    try {
      if (!skill.has_form) {
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
      const refreshedInstalled = await loadInstalledSkills();
      await refreshAvailableSkills(refreshedInstalled);
    } catch (err: unknown) {
      setInstallSkillError(err instanceof Error ? err.message : "Failed to install skill");
    } finally {
      setInstallingSkill(false);
    }
  };

  const handleConnectGoogleDriveSkill = async () => {
    if (!selectedSkill) return;
    setConnectingSkillId(selectedSkill.skill_id);
    setInstallSkillError(null);
    try {
      const returnTo = `${window.location.origin}/dashboard/agents/${agent.agent_id}/skills`;
      const response = await skillApiService.startGoogleDriveOAuth({
        agent_id: agent.agent_id,
        skill_id: selectedSkill.skill_id,
        return_to: returnTo,
      });
      window.location.href = response.authorize_url;
    } catch (err: unknown) {
      setInstallSkillError(err instanceof Error ? err.message : "Failed to connect Google Drive");
      setConnectingSkillId(null);
    }
  };

  const handleToggleSkill = async (skill: InstalledSkill) => {
    setUpdatingSkillId(skill.skill_id);
    try {
      const updated = await skillApiService.updateInstalledSkill(agent.agent_id, skill.skill_id, {
        enabled: !skill.enabled,
      });
      setInstalledSkills((prev) =>
        prev.map((item) => (item.skill_id === updated.skill_id ? updated : item))
      );
    } catch (err) {
      console.error("Error toggling skill:", err);
    } finally {
      setUpdatingSkillId(null);
    }
  };

  const handleUpdateSkillConfig = async (skill: InstalledSkill, data: Record<string, FormValue>) => {
    setUpdatingSkillId(skill.skill_id);
    try {
      const payload: Record<string, string> = {};
      for (const [key, value] of Object.entries(data)) {
        if (typeof value === "string") payload[key] = value;
      }
      const updated = await skillApiService.updateInstalledSkill(agent.agent_id, skill.skill_id, {
        config: payload,
      });
      setInstalledSkills((prev) =>
        prev.map((item) => (item.skill_id === updated.skill_id ? updated : item))
      );
    } catch (err) {
      console.error("Error updating skill config:", err);
    } finally {
      setUpdatingSkillId(null);
    }
  };

  const handleUninstallSkill = async (skillId: string) => {
    setUninstallingSkillId(skillId);
    try {
      await skillApiService.uninstallSkill(agent.agent_id, skillId);
      setInstalledSkills((prev) => prev.filter((skill) => skill.skill_id !== skillId));
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
            <Button size="sm" onClick={openSkillDialog}>
              <Plus style={{ height: "1rem", width: "1rem", marginRight: "0.375rem" }} />
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
              {installedSkills.map((skill) => (
                <div key={skill.skill_id} style={{ border: "1px solid var(--border-subtle)", borderRadius: "0.75rem", padding: "1rem" }}>
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
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                      <Button variant="outline" size="sm" onClick={() => handleToggleSkill(skill)} disabled={updatingSkillId === skill.skill_id}>
                        {skill.enabled ? (
                          <>
                            <PowerOff className="h-4 w-4 mr-2" />
                            Disable
                          </>
                        ) : (
                          <>
                            <Power className="h-4 w-4 mr-2" />
                            Enable
                          </>
                        )}
                      </Button>
                      <Button variant="destructive" size="sm" onClick={() => handleUninstallSkill(skill.skill_id)} disabled={uninstallingSkillId === skill.skill_id}>
                        {uninstallingSkillId === skill.skill_id ? "Removing..." : "Uninstall"}
                      </Button>
                      {Object.keys(skill.config).length > 0 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleUpdateSkillConfig(skill, skill.config)}
                          disabled={updatingSkillId === skill.skill_id}
                        >
                          {updatingSkillId === skill.skill_id ? "Saving..." : "Refresh Config"}
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={isSkillDialogOpen} onOpenChange={setIsSkillDialogOpen}>
        <DialogContent style={{ maxWidth: "56rem" }}>
          <DialogHeader>
            <DialogTitle>Add Skill</DialogTitle>
            <DialogDescription>
              Install a skill and configure it for this agent.
            </DialogDescription>
          </DialogHeader>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <div style={{ border: "1px solid var(--border-subtle)", borderRadius: "0.5rem", padding: "0.75rem", maxHeight: "18rem", overflowY: "auto" }}>
              {availableSkills.length === 0 ? (
                <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>No additional skills available.</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {availableSkills.map((skill) => (
                    <button
                      key={skill.skill_id}
                      type="button"
                      onClick={() => void selectSkillForInstall(skill)}
                      style={{
                        border: selectedSkill?.skill_id === skill.skill_id ? "2px solid var(--gradient-start)" : "1px solid var(--border-subtle)",
                        borderRadius: "0.5rem",
                        background: "transparent",
                        color: "inherit",
                        padding: "0.75rem",
                        textAlign: "left",
                        cursor: "pointer",
                      }}
                    >
                      <div style={{ fontWeight: 500, color: "var(--text-primary)", marginBottom: "0.25rem" }}>{skill.name}</div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{skill.description}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div>
              {!selectedSkill ? (
                <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>Select a skill to configure and install.</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  <div>
                    <p style={{ fontWeight: 600, color: "var(--text-primary)" }}>{selectedSkill.name}</p>
                    <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>{selectedSkill.description}</p>
                    {selectedSkill.requires_oauth && (
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
                  {selectedSkill.requires_oauth && !selectedSkill.oauth_connected && (
                    <Button onClick={handleConnectGoogleDriveSkill} disabled={connectingSkillId === selectedSkill.skill_id}>
                      {connectingSkillId === selectedSkill.skill_id ? "Connecting..." : "Connect Google Drive"}
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
                  {!selectedSkillSchema && (!selectedSkill.requires_oauth || selectedSkill.oauth_connected) && (
                    <Button onClick={() => void handleInstallSkill({})} disabled={installingSkill}>
                      {installingSkill ? "Installing..." : "Install Skill"}
                    </Button>
                  )}
                </div>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
