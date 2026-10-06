/**
 * Dummy data for the automations tutorial.
 *
 * The sandboxes render the real workspace components, so everything here has the
 * exact shape the API returns. The catalog items and trigger forms mirror
 * `agent_invocation`, `send_email`, and `api/src/automations/triggers/schemas.py`;
 * when those change, update the copies here so the tutorial shows what users see.
 */

import type {
  AutomationActionCatalogItem,
  AutomationEdge,
  AutomationGraphResponse,
  AutomationNode,
  AutomationTrigger,
  AutomationTriggerType,
} from "../../../types/automation";
import type { FormSchema } from "../../../types/form";

const AUTOMATION_ID = "tutorial-daily-briefing";
const CREATED_AT = "2026-10-01T08:00:00Z";

export const SAMPLE_AGENT = { value: "agent-research", label: "Research Assistant" };
export const SAMPLE_RECIPIENT = "you@example.com";
export const BRIEFING_PROMPT =
  "Write a short morning briefing on {{ input.topic }}. Use three bullet points and keep it under 150 words.";
export const BRIEFING_BODY = "{{ steps.summary.output.result.response_text }}";

const AGENT_STEP_ID = "action-summary";
const EMAIL_STEP_ID = "action-email";

export const SEND_EMAIL_INSTALL_FORM: FormSchema = {
  form_name: "Send Email",
  submit_path: "",
  form_inputs: [
    {
      input_type: "text",
      name: "to",
      label: "Recipient emails",
      attr: { placeholder: "name@example.com, team@example.com" },
    },
  ],
};

const INVOKE_AGENT: AutomationActionCatalogItem = {
  action_type: "skill_action",
  skill_id: "agent_invocation",
  installed_skill_id: "agent_invocation",
  skill_name: "Invoke Agent",
  action: "invoke",
  label: "Invoke Agent: invoke",
  description: "Invoke an agent and return response text, runtime events, and saved message ids.",
  input_schema: {
    type: "object",
    required: ["prompt_template", "agent_id"],
    properties: {
      agent_id: { type: "string" },
      prompt_template: { type: "string" },
    },
  },
  action_form: {
    form_name: "Invoke Agent",
    submit_path: "",
    form_inputs: [
      // Real forms load the owner's agents; the tutorial ships one sample agent.
      { input_type: "select", name: "agent_id", label: "Agent", options: [SAMPLE_AGENT] },
      {
        input_type: "text_area",
        name: "prompt_template",
        label: "Prompt template",
        attr: { rows: "6", smart_values: "true" },
      },
    ],
  },
  available: true,
  configured: true,
  enabled: true,
  disabled_reason: null,
  connectors: [],
};

const SEND_EMAIL_BASE: Omit<
  AutomationActionCatalogItem,
  "available" | "configured" | "enabled" | "installed_skill_id"
> = {
  action_type: "skill_action",
  skill_id: "send_email",
  skill_name: "Send Email",
  action: "send",
  label: "Send Email: send",
  description: "Send an email to the configured recipients and return delivery status.",
  input_schema: {
    type: "object",
    required: ["subject", "body"],
    properties: { subject: { type: "string" }, body: { type: "string" } },
  },
  action_form: {
    form_name: "Send Email",
    submit_path: "",
    form_inputs: [
      { input_type: "text", name: "subject", label: "Subject", attr: { smart_values: "true" } },
      {
        input_type: "text_area",
        name: "body",
        label: "Body",
        attr: { rows: "6", smart_values: "true" },
      },
    ],
  },
  connectors: [],
};

/** Send Email before its recipients are set: picking it opens the setup dialog. */
const SEND_EMAIL_NEEDS_SETUP: AutomationActionCatalogItem = {
  ...SEND_EMAIL_BASE,
  installed_skill_id: null,
  available: false,
  configured: false,
  enabled: false,
  disabled_reason: "Skill requires configuration before use",
  install_schema: SEND_EMAIL_INSTALL_FORM,
};

export const SEND_EMAIL_INSTALLED_ID = "send_email:you-example-com";

export function installedSendEmail(installedSkillId: string): AutomationActionCatalogItem {
  return {
    ...SEND_EMAIL_BASE,
    installed_skill_id: installedSkillId,
    available: true,
    configured: true,
    enabled: true,
    disabled_reason: null,
  };
}

const GMAIL_SEARCH: AutomationActionCatalogItem = {
  action_type: "skill_action",
  skill_id: "google_mail",
  installed_skill_id: null,
  skill_name: "Gmail",
  action: "search",
  label: "Gmail: search",
  description: "Search the connected Gmail inbox.",
  input_schema: { type: "object", properties: {} },
  action_form: null,
  available: false,
  configured: false,
  enabled: false,
  disabled_reason: "Missing connected connectors: GoogleMail",
  connectors: [
    { connector_id: "google_mail", provider_name: "GoogleMail", required: true, connected: false },
  ],
};

export function tutorialCatalog(emailInstalled: boolean): AutomationActionCatalogItem[] {
  return [
    INVOKE_AGENT,
    emailInstalled ? installedSendEmail(SEND_EMAIL_INSTALLED_ID) : SEND_EMAIL_NEEDS_SETUP,
    GMAIL_SEARCH,
  ];
}

/** The forms `GET /automations/{id}/triggers/forms/{type}` returns for a single-start graph. */
export const TRIGGER_FORMS: Partial<Record<AutomationTriggerType, FormSchema>> = {
  manual: {
    form_name: "Manual Trigger",
    submit_path: "",
    form_inputs: [
      { input_type: "text", name: "name", label: "Name", attr: { placeholder: "Manual run" } },
      {
        input_type: "select",
        name: "enabled",
        label: "Status",
        value: "true",
        options: [
          { value: "true", label: "Enabled" },
          { value: "false", label: "Disabled" },
        ],
      },
    ],
  },
  schedule: {
    form_name: "Schedule Trigger",
    submit_path: "",
    form_inputs: [
      { input_type: "text", name: "name", label: "Name", attr: { placeholder: "Weekday cleanup" } },
      {
        // The real form also has a "Suggest" button that writes cron from plain
        // English; it needs a signed-in account, so the tutorial leaves it out.
        input_type: "text",
        name: "cron_expression",
        label: "Cron expression",
        attr: {
          placeholder: "0 9 * * 1-5",
          help_text: "Standard 5-field cron: minute hour day month weekday.",
        },
      },
      {
        input_type: "text",
        name: "timezone",
        label: "Timezone",
        value: "UTC",
        attr: { placeholder: "UTC" },
      },
      {
        input_type: "select",
        name: "enabled",
        label: "Status",
        value: "true",
        options: [
          { value: "true", label: "Enabled" },
          { value: "false", label: "Disabled" },
        ],
      },
      {
        input_type: "key_value",
        name: "input",
        label: "Input",
        attr: {
          help_text:
            "Optional fixed values passed to every scheduled run. Steps read them as {{ input.<key> }}; the values themselves are used as typed.",
          empty_text: "No input values will be passed to the scheduled automation.",
          key_placeholder: "topic",
          value_placeholder: "AI agent news",
          add_label: "Add input",
        },
      },
    ],
  },
};

export type TutorialStage = "created" | "agent" | "email" | "scheduled";

function node(
  node_id: string,
  type: AutomationNode["type"],
  name: string,
  extra: Partial<AutomationNode> = {}
): AutomationNode {
  return {
    node_id,
    automation_id: AUTOMATION_ID,
    type,
    name,
    position: {},
    config: {},
    created_at: CREATED_AT,
    ...extra,
  };
}

function chainEdges(nodeIds: string[]): AutomationEdge[] {
  return nodeIds.slice(1).map((target, index) => ({
    edge_id: `edge-${nodeIds[index]}-${target}`,
    automation_id: AUTOMATION_ID,
    source_node_id: nodeIds[index],
    target_node_id: target,
    label: "next",
    created_at: CREATED_AT,
  }));
}

function trigger(
  trigger_id: string,
  type: AutomationTriggerType,
  name: string,
  config: Record<string, unknown> = {}
): AutomationTrigger {
  return {
    trigger_id,
    automation_id: AUTOMATION_ID,
    type,
    name,
    enabled: true,
    entry_node_id: "start",
    config,
    created_at: CREATED_AT,
  };
}

const AGENT_STEP = node(AGENT_STEP_ID, "action", "Write the briefing", {
  alias: "summary",
  config: {
    action_type: "skill_action",
    installed_skill_id: "agent_invocation",
    skill_id: "agent_invocation",
    action: "invoke",
    arguments: { agent_id: SAMPLE_AGENT.value, prompt_template: BRIEFING_PROMPT },
  },
});

const EMAIL_STEP = node(EMAIL_STEP_ID, "action", "Email it to me", {
  alias: "email_me",
  config: {
    action_type: "skill_action",
    installed_skill_id: SEND_EMAIL_INSTALLED_ID,
    skill_id: "send_email",
    action: "send",
    arguments: { subject: "Your briefing: {{ input.topic }}", body: BRIEFING_BODY },
  },
});

/** The automation as it stands at the start of each tutorial step. */
export function tutorialGraph(stage: TutorialStage): AutomationGraphResponse {
  const steps = {
    created: [],
    agent: [AGENT_STEP],
    email: [AGENT_STEP, EMAIL_STEP],
    scheduled: [AGENT_STEP, EMAIL_STEP],
  }[stage];
  const nodes = [node("start", "start", "Start"), ...steps, node("final", "final", "Done")];
  const triggers = [trigger("trigger-manual", "manual", "Manual")];
  if (stage === "scheduled") {
    triggers.push(
      trigger("trigger-schedule", "schedule", "Weekday briefing", {
        cron_expression: "0 8 * * 1-5",
        timezone: "Europe/London",
        input: { topic: "AI agent news" },
      })
    );
  }

  return {
    automation: {
      automation_id: AUTOMATION_ID,
      title: "Daily briefing",
      description: "Emails me a short briefing every weekday morning.",
      status: "draft",
      version: 1,
      created_by: SAMPLE_RECIPIENT,
      created_at: CREATED_AT,
    },
    nodes,
    edges: chainEdges(nodes.map((item) => item.node_id)),
    triggers,
  };
}

/**
 * Stand-ins for what each action returns, keyed by `skill_id.action`. Arguments
 * arrive with smart values already rendered, as they do on the server.
 */
export const SIMULATED_ACTIONS: Record<
  string,
  (args: Record<string, unknown>, config: Record<string, unknown>) => Record<string, unknown>
> = {
  "agent_invocation.invoke": (args) => ({
    response_text: [
      "Good morning! This is a sample reply; in your workspace your agent writes it.",
      "",
      `Prompt it received: ${String(args.prompt_template ?? "")}`,
      "",
      "• First headline worth knowing about.",
      "• A second development, with why it matters.",
      "• One thing to keep an eye on this week.",
    ].join("\n"),
    events: [],
    message_ids: { user_message_id: "msg-user-1", assistant_message_id: "msg-assistant-1" },
  }),
  "send_email.send": (_args, config) => {
    const recipients = String(config.to ?? SAMPLE_RECIPIENT)
      .split(",")
      .map((email) => email.trim())
      .filter(Boolean);
    return {
      sent: true,
      total: recipients.length,
      succeeded: recipients.length,
      failed: 0,
      recipients: recipients.map((email) => ({ email, sent: true })),
    };
  },
};
