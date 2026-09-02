import { useEffect, useMemo, useRef, useState } from "react";
import { Boxes, Check, Plus, Power, PowerOff, Settings2, Trash2, Wrench } from "lucide-react";

import { SchemaForm } from "../../../components/forms";
import { Stack } from "../../../components/layout";
import {
  Button,
  Card,
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogSection,
  DialogTitle,
  InlineEmptyState,
  LoadingState,
  SearchInput,
  StatusBadge,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../../components/ui";
import { connectorApiService } from "../../../services/connectors";
import { skillApiService } from "../../../services/skills";
import type { FormValue, FormSchema } from "../../../types/form";
import type { InstalledSkill, SkillCatalogItem, SkillConnectorStatus } from "../../../types/skills";
import { useAgentDetailContext } from "./types";
import "./AgentSkillsPage.css";

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

function skillConfigPayload(data: Record<string, FormValue>): Record<string, string | Record<string, string>> {
  const payload: Record<string, string | Record<string, string>> = {};
  for (const [key, value] of Object.entries(data)) {
    if (typeof value === "string") {
      payload[key] = value;
    } else if (value && !Array.isArray(value) && !(value instanceof FileList)) {
      payload[key] = value;
    }
  }
  return payload;
}

function getSkillCategory(skill: { namespace: string }): string {
  return skill.namespace.split(".")[0]?.trim() || "other";
}

function prettifyCategory(category: string): string {
  return category
    .split(/[-_]/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

interface NamedSkill {
  name: string;
  namespace: string;
}

function groupSkillsByNamespace<T extends NamedSkill>(skills: T[]): Array<{ namespace: string; label: string; skills: T[] }> {
  const groups = new Map<string, T[]>();

  skills.forEach((skill) => {
    const namespace = getSkillCategory(skill);
    groups.set(namespace, [...(groups.get(namespace) ?? []), skill]);
  });

  return Array.from(groups.entries())
    .sort(([left], [right]) => prettifyCategory(left).localeCompare(prettifyCategory(right)))
    .map(([namespace, namespaceSkills]) => ({
      namespace,
      label: prettifyCategory(namespace),
      skills: namespaceSkills.sort((left, right) => left.name.localeCompare(right.name)),
    }));
}

type SkillsTab = "discover" | "installed";

export function AgentSkillsPage() {
  const { agent } = useAgentDetailContext();
  const [installedSkills, setInstalledSkills] = useState<InstalledSkill[]>([]);
  const [availableSkills, setAvailableSkills] = useState<SkillCatalogItem[]>([]);
  const [loadingSkills, setLoadingSkills] = useState(false);
  const [isSkillDialogOpen, setIsSkillDialogOpen] = useState(false);
  const [selectedSkill, setSelectedSkill] = useState<SkillCatalogItem | null>(null);
  const [selectedSkillSchema, setSelectedSkillSchema] = useState<FormSchema | null>(null);
  const [activeTab, setActiveTab] = useState<SkillsTab>("discover");
  const [skillSearch, setSkillSearch] = useState("");
  const [installSkillError, setInstallSkillError] = useState<string | null>(null);
  const [installingSkill, setInstallingSkill] = useState(false);
  const [isConfigDialogOpen, setIsConfigDialogOpen] = useState(false);
  const [configuringSkill, setConfiguringSkill] = useState<InstalledSkill | null>(null);
  const [configSkillSchema, setConfigSkillSchema] = useState<FormSchema | null>(null);
  const [configInitialValues, setConfigInitialValues] = useState<Record<string, FormValue>>({});
  const [configSkillError, setConfigSkillError] = useState<string | null>(null);
  const [configCredentialOrigin, setConfigCredentialOrigin] = useState<string | null>(null);
  const [connectingSkillId, setConnectingSkillId] = useState<string | null>(null);
  const [updatingSkillId, setUpdatingSkillId] = useState<string | null>(null);
  const [uninstallingSkillId, setUninstallingSkillId] = useState<string | null>(null);
  const handledSkillOAuthCallbackRef = useRef(false);
  const handledConfigDeepLinkRef = useRef(false);

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

  const installedSkillCounts = useMemo(() => {
    const counts = new Map<string, number>();
    installedSkills.forEach((skill) => {
      counts.set(skill.skill_id, (counts.get(skill.skill_id) ?? 0) + 1);
    });
    return counts;
  }, [installedSkills]);

  const filteredAvailableSkills = useMemo(() => {
    const normalizedSearch = skillSearch.trim().toLowerCase();
    return availableSkills
      .filter((skill) => {
        if (!normalizedSearch) return true;
        return [skill.name, skill.description, skill.namespace]
          .some((value) => value.toLowerCase().includes(normalizedSearch));
      });
  }, [availableSkills, skillSearch]);

  const filteredInstalledSkills = useMemo(() => {
    const normalizedSearch = skillSearch.trim().toLowerCase();
    return installedSkills.filter((skill) => {
      if (!normalizedSearch) return true;
      return [skill.name, skill.description, skill.namespace]
        .some((value) => value.toLowerCase().includes(normalizedSearch));
    });
  }, [installedSkills, skillSearch]);

  const discoverGroups = useMemo(
    () => groupSkillsByNamespace(filteredAvailableSkills),
    [filteredAvailableSkills]
  );
  const installedGroups = useMemo(
    () => groupSkillsByNamespace(filteredInstalledSkills),
    [filteredInstalledSkills]
  );

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

        const callbackSkillRepeatable = callbackSkill?.repeatable === true;
        const alreadyInstalled = currentInstalled.some((skill) => skill.skill_id === callbackSkillId);
        if (!alreadyInstalled || callbackSkillRepeatable) {
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

  const selectSkillForInstall = async (skill: SkillCatalogItem) => {
    if ((installedSkillCounts.get(skill.skill_id) ?? 0) > 0 && !skill.repeatable) return;
    setInstallSkillError(null);
    setSelectedSkill(skill);
    setSelectedSkillSchema(null);
    setIsSkillDialogOpen(true);
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
      await skillApiService.installSkill(agent.agent_id, selectedSkill.skill_id, { config: skillConfigPayload(data) });
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

  const openConfigureSkill = async (
    skill: InstalledSkill,
    options?: { focus?: string | null; credentialOrigin?: string | null }
  ) => {
    const installedSkillId = skill.installed_skill_id ?? skill.skill_id;
    setConfiguringSkill(skill);
    setConfigSkillSchema(null);
    setConfigSkillError(null);
    setConfigCredentialOrigin(options?.credentialOrigin ?? null);
    setIsConfigDialogOpen(true);
    setUpdatingSkillId(installedSkillId);
    try {
      const schema = await skillApiService.getSkillInstallSchema(skill.skill_id);
      const initialValues: Record<string, FormValue> = { ...skill.config };
      if (options?.focus === "default_credentials" && options.credentialOrigin) {
        const current = initialValues.default_credentials;
        initialValues.default_credentials = {
          ...(current && typeof current === "object" && !(current instanceof FileList) && !Array.isArray(current)
            ? current
            : {}),
          [options.credentialOrigin]: "",
        };
      }
      setConfigInitialValues(initialValues);
      setConfigSkillSchema(schema);
    } catch (err: unknown) {
      setConfigSkillError(err instanceof Error ? err.message : "Failed to load skill configuration");
    } finally {
      setUpdatingSkillId(null);
    }
  };

  const handleUpdateSkillConfig = async (skill: InstalledSkill, data: Record<string, FormValue>) => {
    const installedSkillId = skill.installed_skill_id ?? skill.skill_id;
    setUpdatingSkillId(installedSkillId);
    setConfigSkillError(null);
    try {
      const updated = await skillApiService.updateInstalledSkill(agent.agent_id, installedSkillId, {
        config: skillConfigPayload(data),
      });
      setInstalledSkills((prev) =>
        prev.map((item) => ((item.installed_skill_id ?? item.skill_id) === updated.installed_skill_id ? updated : item))
      );
      setIsConfigDialogOpen(false);
      setConfiguringSkill(null);
      setConfigSkillSchema(null);
      setConfigInitialValues({});
      setConfigCredentialOrigin(null);
    } catch (err: unknown) {
      console.error("Error updating skill config:", err);
      setConfigSkillError(err instanceof Error ? err.message : "Failed to update skill configuration");
    } finally {
      setUpdatingSkillId(null);
    }
  };

  const handleConnectA2ARemoteOAuth = async () => {
    if (!configuringSkill) return;
    const installedSkillId = configuringSkill.installed_skill_id ?? configuringSkill.skill_id;
    setConnectingSkillId(installedSkillId);
    setConfigSkillError(null);
    try {
      const returnTo = `${window.location.origin}/dashboard/agents/${agent.agent_id}/skills`;
      const response = await skillApiService.startA2ARemoteOAuth({
        agent_id: agent.agent_id,
        installed_skill_id: installedSkillId,
        target_origin: configCredentialOrigin,
        return_to: returnTo,
      });
      window.location.href = response.authorize_url;
    } catch (err: unknown) {
      setConfigSkillError(err instanceof Error ? err.message : "Failed to start Agent2Agent OAuth");
      setConnectingSkillId(null);
    }
  };

  useEffect(() => {
    if (handledConfigDeepLinkRef.current || installedSkills.length === 0) return;

    const params = new URLSearchParams(window.location.search);
    const targetSkillId = params.get("configure_skill") || params.get("installed_skill_id");
    if (!targetSkillId) return;

    const targetSkill = installedSkills.find((skill) => (skill.installed_skill_id ?? skill.skill_id) === targetSkillId);
    if (!targetSkill) return;

    handledConfigDeepLinkRef.current = true;
    void openConfigureSkill(targetSkill, {
      focus: params.get("focus"),
      credentialOrigin: params.get("credential_origin"),
    });
    const a2aOAuthStatus = params.get("a2a_oauth");
    if (a2aOAuthStatus === "success") {
      setConfigSkillError(null);
    } else if (a2aOAuthStatus === "error") {
      setConfigSkillError(params.get("reason") || "Agent2Agent OAuth connection failed");
    }
  }, [installedSkills]);

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
      <div className="agent-skills-page">
        <header className="agent-skills-page__header">
          <h2 className="agent-skills-page__title">Skills</h2>
          <p className="agent-skills-page__description">
            Extend what this agent can do with reusable capabilities.
          </p>
        </header>

        <SearchInput
          aria-label={`Search ${activeTab} skills`}
          value={skillSearch}
          onChange={(event) => setSkillSearch(event.target.value)}
          placeholder={activeTab === "discover" ? "Search available skills" : "Search installed skills"}
          className="agent-skills-page__search"
        />

        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as SkillsTab)}>
          <TabsList className="agent-skills-page__tabs">
            <TabsTrigger value="discover" className="agent-skills-page__tab">
              Discover
              <span className="agent-skills-page__tab-count">{availableSkills.length}</span>
            </TabsTrigger>
            <TabsTrigger value="installed" className="agent-skills-page__tab">
              Installed
              <span className="agent-skills-page__tab-count">{installedSkills.length}</span>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="discover" className="agent-skills-page__content">
            {loadingSkills && availableSkills.length === 0 ? (
              <LoadingState />
            ) : availableSkills.length === 0 ? (
              <InlineEmptyState
                icon={Boxes}
                title="No skills available"
                description="There are no skills in the catalog yet."
              />
            ) : discoverGroups.length === 0 ? (
              <InlineEmptyState
                icon={Wrench}
                title="No matching skills"
                description="Try a different name, description, or namespace."
              />
            ) : (
              <div className="agent-skills-page__groups">
                {discoverGroups.map((group) => (
                  <section key={group.namespace} className="agent-skills-group">
                    <div className="agent-skills-group__heading">
                      <Boxes aria-hidden="true" />
                      <h3>{group.label}</h3>
                      <span>{group.skills.length}</span>
                    </div>
                    <div className="agent-skills-group__grid">
                      {group.skills.map((skill) => {
                        const installedCount = installedSkillCounts.get(skill.skill_id) ?? 0;
                        const installed = installedCount > 0;
                        const installBlocked = installed && !skill.repeatable;

                        return (
                          <Card key={skill.skill_id} className="agent-skill-card">
                            <div className="agent-skill-card__icon" aria-hidden="true">
                              {skill.name.charAt(0).toUpperCase()}
                            </div>
                            <div className="agent-skill-card__body">
                              <div className="agent-skill-card__title-row">
                                <h4>{skill.name}</h4>
                                {installed && (
                                  <StatusBadge
                                    status="success"
                                    size="sm"
                                    label={skill.repeatable ? `${installedCount} installed` : "Installed"}
                                  />
                                )}
                              </div>
                              <p>{skill.description}</p>
                              <span className="agent-skill-card__namespace">{skill.namespace}</span>
                            </div>
                            <Button
                              type="button"
                              variant="outline"
                              size="icon"
                              className="agent-skill-card__primary-action"
                              disabled={installBlocked}
                              onClick={() => void selectSkillForInstall(skill)}
                              aria-label={installBlocked ? `${skill.name} is installed` : `Install ${skill.name}`}
                              title={installBlocked ? "Installed" : "Install skill"}
                            >
                              {installBlocked ? <Check /> : <Plus />}
                            </Button>
                          </Card>
                        );
                      })}
                    </div>
                  </section>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="installed" className="agent-skills-page__content">
            {loadingSkills ? (
              <LoadingState />
            ) : installedSkills.length === 0 ? (
              <InlineEmptyState
                icon={Wrench}
                title="No skills installed"
                description="Choose a skill from Discover to add capabilities to this agent."
              />
            ) : installedGroups.length === 0 ? (
              <InlineEmptyState
                icon={Wrench}
                title="No matching installed skills"
                description="Try a different name, description, or namespace."
              />
            ) : (
              <div className="agent-skills-page__groups">
                {installedGroups.map((group) => (
                  <section key={group.namespace} className="agent-skills-group">
                    <div className="agent-skills-group__heading">
                      <Boxes aria-hidden="true" />
                      <h3>{group.label}</h3>
                      <span>{group.skills.length}</span>
                    </div>
                    <div className="agent-skills-group__grid">
                      {group.skills.map((skill) => {
                        const installedSkillId = skill.installed_skill_id ?? skill.skill_id;
                        const configuredFields = Object.keys(skill.config);

                        return (
                          <Card key={installedSkillId} className="agent-skill-card agent-skill-card--installed">
                            <div className="agent-skill-card__icon" aria-hidden="true">
                              {skill.name.charAt(0).toUpperCase()}
                            </div>
                            <div className="agent-skill-card__body">
                              <div className="agent-skill-card__title-row">
                                <h4>{skill.name}</h4>
                                <StatusBadge
                                  status={skill.enabled ? "active" : "inactive"}
                                  size="sm"
                                  label={skill.enabled ? "Enabled" : "Disabled"}
                                />
                              </div>
                              <p>{skill.description}</p>
                              {configuredFields.length > 0 && (
                                <span className="agent-skill-card__configured">
                                  Configured: {configuredFields.join(", ")}
                                </span>
                              )}
                              <span className="agent-skill-card__namespace">{skill.namespace}</span>
                            </div>
                            <div className="agent-skill-card__actions">
                              <Button
                                variant="ghost"
                                size="action"
                                onClick={() => handleToggleSkill(skill)}
                                disabled={updatingSkillId === installedSkillId}
                              >
                                {skill.enabled ? <PowerOff /> : <Power />}
                                {skill.enabled ? "Disable" : "Enable"}
                              </Button>
                              <Button
                                variant="ghost"
                                size="action"
                                onClick={() => void openConfigureSkill(skill)}
                                disabled={updatingSkillId === installedSkillId}
                              >
                                <Settings2 />
                                Configure
                              </Button>
                              <Button
                                variant="destructive"
                                size="action"
                                onClick={() => handleUninstallSkill(skill)}
                                disabled={uninstallingSkillId === installedSkillId}
                              >
                                <Trash2 />
                                {uninstallingSkillId === installedSkillId ? "Removing..." : "Uninstall"}
                              </Button>
                            </div>
                          </Card>
                        );
                      })}
                    </div>
                  </section>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>

      <Dialog
        open={isSkillDialogOpen}
        onOpenChange={(open) => {
          setIsSkillDialogOpen(open);
          if (!open) {
            setSelectedSkill(null);
            setSelectedSkillSchema(null);
            setInstallSkillError(null);
          }
        }}
      >
        <DialogContent
          className="agent-skill-install-dialog"
          style={{ width: "min(92vw, 44rem)", maxWidth: "44rem" }}
        >
          <DialogHeader>
            <DialogTitle>{selectedSkill ? `Install ${selectedSkill.name}` : "Install Skill"}</DialogTitle>
            <DialogDescription>
              Configure this reusable capability for the agent.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="agent-skill-install-dialog__body">
            <section className="agent-skill-install-dialog__config">
              {!selectedSkill ? (
                <DialogSection style={{ borderStyle: "dashed", color: "var(--text-muted)" }}>
                  <p style={{ fontSize: "0.8125rem", lineHeight: 1.5 }}>
                    The selected skill could not be loaded. Close this dialog and choose it again.
                  </p>
                </DialogSection>
              ) : (
                <Stack gap="sm">
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
                    <div className="agent-skill-dialog__error">
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
                </Stack>
              )}
            </section>
          </DialogBody>
        </DialogContent>
      </Dialog>

      <Dialog open={isConfigDialogOpen} onOpenChange={setIsConfigDialogOpen}>
        <DialogContent
          className="agent-skill-config-dialog"
          style={{ width: "min(92vw, 44rem)", maxWidth: "44rem" }}
        >
          <DialogHeader>
            <DialogTitle>{configuringSkill ? `Configure ${configuringSkill.name}` : "Configure Skill"}</DialogTitle>
            <DialogDescription>
              Update this installed skill's runtime configuration and credentials.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="agent-skill-config-dialog__body">
            <Stack gap="md">
              {configSkillError && (
                <div className="agent-skill-dialog__error">
                  {configSkillError}
                </div>
              )}
              {configuringSkill && configSkillSchema ? (
                <>
                  {configuringSkill.skill_id === "agent2agent_client" && configCredentialOrigin && (
                    <DialogSection>
                      <Stack gap="sm">
                        <div>
                          <p style={{ fontWeight: 600, color: "var(--text-primary)" }}>Agent2Agent OAuth</p>
                          <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>{configCredentialOrigin}</p>
                        </div>
                        <Button
                          type="button"
                          onClick={() => void handleConnectA2ARemoteOAuth()}
                          disabled={connectingSkillId === (configuringSkill.installed_skill_id ?? configuringSkill.skill_id)}
                        >
                          {connectingSkillId === (configuringSkill.installed_skill_id ?? configuringSkill.skill_id)
                            ? "Connecting..."
                            : "Connect Agent2Agent OAuth"}
                        </Button>
                      </Stack>
                    </DialogSection>
                  )}
                  <SchemaForm
                    key={`${configuringSkill.installed_skill_id ?? configuringSkill.skill_id}-${JSON.stringify(configInitialValues)}`}
                    schema={configSkillSchema}
                    initialValues={configInitialValues}
                    onSubmit={(data) => handleUpdateSkillConfig(configuringSkill, data)}
                    onCancel={() => {
                      setIsConfigDialogOpen(false);
                      setConfiguringSkill(null);
                      setConfigSkillSchema(null);
                      setConfigInitialValues({});
                      setConfigCredentialOrigin(null);
                      setConfigSkillError(null);
                    }}
                    submitLabel={updatingSkillId ? "Saving..." : "Save Configuration"}
                    isLoading={Boolean(updatingSkillId)}
                  />
                </>
              ) : (
                <LoadingState className="agent-skill-dialog__loading" />
              )}
            </Stack>
          </DialogBody>
        </DialogContent>
      </Dialog>
    </>
  );
}
