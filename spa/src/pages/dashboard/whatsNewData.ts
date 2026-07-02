export type ChangeCategory = "new" | "improved" | "fixed" | "developer";

export interface ChangeItem {
  title: string;
  description: string;
  category: ChangeCategory;
}

export interface ChangeLogEntry {
  date: string;
  title: string;
  summary: string;
  items: ChangeItem[];
}

export const changeLogEntries: ChangeLogEntry[] = [
  {
    date: "2026-07-02",
    title: "Design system hardening",
    summary:
      "The dashboard UI is moving to shared layout and control primitives so spacing, buttons, forms, and cards stay consistent across pages.",
    items: [
      {
        title: "Consistent page layouts",
        description:
          "Core dashboard list pages now use shared page, stack, inline, and grid primitives for more predictable margins and card spacing.",
        category: "improved",
      },
      {
        title: "Button and form consistency",
        description:
          "Shared buttons, inputs, textareas, selects, checkboxes, radios, and file inputs now own their sizing and padding instead of relying on page-specific fixes.",
        category: "improved",
      },
      {
        title: "Frontend design audit",
        description:
          "A design audit command now catches raw controls and common button contract violations before they spread to new pages.",
        category: "developer",
      },
      {
        title: "Faster route loading",
        description:
          "Dashboard and public pages are now lazy-loaded so the initial application bundle is smaller and heavy pages load only when needed.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-06-30",
    title: "Agent marketplace",
    summary:
      "Users can publish reusable agents, browse shared templates, inspect instructions, and import configured copies into their own workspace.",
    items: [
      {
        title: "Marketplace browsing",
        description:
          "The Agents page now links to a marketplace where users can search shared agents and open detailed template previews.",
        category: "new",
      },
      {
        title: "Importable agent templates",
        description:
          "Marketplace imports create a private agent copy and ask for the importing user's required skill configuration before installation.",
        category: "new",
      },
      {
        title: "User publishing",
        description:
          "Agents can be published as versioned marketplace templates without copying private skill secrets or OAuth credentials.",
        category: "new",
      },
    ],
  },
  {
    date: "2026-06-29",
    title: "Artifacts and report sharing",
    summary:
      "Generated files are now treated as durable user artifacts that can be opened or downloaded from a central artifact library.",
    items: [
      {
        title: "Artifact library",
        description:
          "Generated reports and files are stored as user-owned artifacts, making them accessible after the skill or automation that created them has finished.",
        category: "new",
      },
      {
        title: "Browser-openable HTML reports",
        description:
          "HTML report artifacts can return a browser view link while still keeping download behavior for normal file access.",
        category: "new",
      },
      {
        title: "Upload File skill",
        description:
          "Agents can save generated text, Markdown, JSON, CSV, code, or HTML as durable artifacts and return a link to the user.",
        category: "new",
      },
    ],
  },
  {
    date: "2026-06-28",
    title: "Async tool execution",
    summary:
      "Long-running skill actions can now run through an async job path while the agent keeps the user informed and resumes with the final result.",
    items: [
      {
        title: "Async skill jobs",
        description:
          "Skill actions can run in the background with persisted job status, progress, result, error state, and seven-day TTL cleanup.",
        category: "new",
      },
      {
        title: "Agent wait tool",
        description:
          "Agents can wait for a bounded duration before checking long-running jobs again, keeping the conversation active without frontend polling.",
        category: "new",
      },
      {
        title: "Long report reliability",
        description:
          "Report generation and other slow tool calls are less likely to hit request timeouts because the runtime can separate job execution from immediate tool response.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-06-27",
    title: "League reports and Riot API skills",
    summary:
      "League of Legends workflows now have dedicated Riot data access and browser-openable report generation.",
    items: [
      {
        title: "League Insights Report skill",
        description:
          "Agents and automations can generate detailed League of Legends HTML reports from Riot match data and save them as artifacts.",
        category: "new",
      },
      {
        title: "Riot LOL API Client skill",
        description:
          "Agents can query Riot League APIs for compact account, match, ranked, mastery, live-game, status, challenge, and clash summaries.",
        category: "new",
      },
      {
        title: "Richer match analysis",
        description:
          "League reports include more match context such as player performance, objectives, recommendations, and rune-related details.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-06-17",
    title: "REST API and external service skills",
    summary:
      "Agents and automations can now call more external systems through generic and provider-specific skills.",
    items: [
      {
        title: "REST Template skill",
        description:
          "Agents and automations can send flexible GET and POST requests with headers, query parameters, body payloads, timeouts, and structured responses.",
        category: "new",
      },
      {
        title: "Safer HTTP responses",
        description:
          "REST responses include bounded body previews, JSON parsing when available, elapsed time, and redaction for sensitive headers.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-06-04",
    title: "Automation triggers are now managed directly",
    summary:
      "Trigger management is becoming its own focused workflow, separate from graph editing.",
    items: [
      {
        title: "Direct trigger loading",
        description:
          "Automation trigger lists now load from trigger records directly, making the page faster and less expensive to operate.",
        category: "improved",
      },
      {
        title: "Separate trigger workspace",
        description:
          "Manual and scheduled automation triggers can be managed from the Triggers page instead of being mixed into the builder canvas.",
        category: "new",
      },
    ],
  },
  {
    date: "2026-06-03",
    title: "Cleaner automation scheduling experience",
    summary:
      "Scheduled automation setup moved toward a simpler trigger-first model with better input controls.",
    items: [
      {
        title: "Scheduled trigger forms",
        description:
          "Schedule creation now asks for cron, timezone, entry step, status, and optional input through structured fields.",
        category: "new",
      },
      {
        title: "Key-value input fields",
        description:
          "Forms can now collect dynamic key-value input without forcing users to write JSON by hand.",
        category: "new",
      },
      {
        title: "Trigger persistence fixes",
        description:
          "Graph saves no longer overwrite triggers created from the trigger management page.",
        category: "fixed",
      },
    ],
  },
  {
    date: "2026-06-01",
    title: "Scheduler foundation",
    summary:
      "A scheduler module was added so agents and automations can run work at planned times.",
    items: [
      {
        title: "Scheduler skill",
        description:
          "Agents can create schedules for follow-up work and send scheduled messages back into the right conversation.",
        category: "new",
      },
      {
        title: "Automation scheduling backend",
        description:
          "The platform can persist scheduled automation runs in DynamoDB and execute them through the scheduler runtime.",
        category: "new",
      },
      {
        title: "Cron support",
        description:
          "Schedules support cron expressions with timezone-aware validation.",
        category: "new",
      },
    ],
  },
  {
    date: "2026-05-31",
    title: "Automation builder and skill actions",
    summary:
      "Automation building became more visual, and skills became reusable as automation actions.",
    items: [
      {
        title: "Builder layout refresh",
        description:
          "The automation builder now keeps the canvas visible while editing steps, testing runs, and inspecting smart values.",
        category: "improved",
      },
      {
        title: "Skills as automation actions",
        description:
          "Supported skills can appear as automation actions without custom action registry code.",
        category: "new",
      },
      {
        title: "Sub-agent invocation support",
        description:
          "Agents can invoke configured sub-agents with isolated in-memory conversation state for each call.",
        category: "new",
      },
      {
        title: "Shared form schema",
        description:
          "Agent creation, skill setup, and automation forms now use a more generic schema-driven form pattern.",
        category: "developer",
      },
    ],
  },
  {
    date: "2026-05-30",
    title: "WordPress connector and pricing updates",
    summary:
      "The platform added WordPress AI connector work and simplified pricing logic.",
    items: [
      {
        title: "WordPress AI connector",
        description:
          "A WordPress connector plugin was added to support site and content workflows.",
        category: "new",
      },
      {
        title: "Pricing model refresh",
        description:
          "Pricing logic was updated to better match the current launch model.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-05-25",
    title: "Railway packaging and widget polish",
    summary:
      "Deployment and widget work made the platform easier to run and embed.",
    items: [
      {
        title: "Railway backend packaging",
        description:
          "The backend was packaged for Railway deployment so the product can run outside the previous AWS-only shape.",
        category: "developer",
      },
      {
        title: "Widget UI updates",
        description:
          "The website widget received UI improvements and an updated script package.",
        category: "improved",
      },
      {
        title: "Image generation streaming endpoint",
        description:
          "An image generation stream endpoint was added for richer media workflows.",
        category: "new",
      },
    ],
  },
  {
    date: "2026-05-24",
    title: "Image generation and downloadable plugins",
    summary:
      "The platform expanded beyond text workflows with image generation and plugin downloads.",
    items: [
      {
        title: "Image generation",
        description:
          "Agents gained image generation support for visual content workflows.",
        category: "new",
      },
      {
        title: "Plugin downloads",
        description:
          "Plugins can now be published and downloaded through generated artifacts.",
        category: "new",
      },
      {
        title: "Automation polling timeout fix",
        description:
          "Long-running automation polling was adjusted to avoid connection timeout issues.",
        category: "fixed",
      },
    ],
  },
  {
    date: "2026-05-23",
    title: "Text generation and connector authentication",
    summary:
      "Core API and connector foundations improved for authenticated integrations.",
    items: [
      {
        title: "Text generation endpoint",
        description:
          "A dedicated API-only text generation endpoint was added.",
        category: "new",
      },
      {
        title: "Connector authentication",
        description:
          "Connector authentication was separated so integrations can be authorized more cleanly.",
        category: "new",
      },
    ],
  },
  {
    date: "2026-05-21",
    title: "Automation builder launch",
    summary:
      "The first automation builder experience was added for customizable workflows.",
    items: [
      {
        title: "Automation builder",
        description:
          "Users can create customizable automations that combine agents, steps, and workflow logic.",
        category: "new",
      },
    ],
  },
  {
    date: "2026-05-17",
    title: "Conversation reliability and agent invocation",
    summary:
      "Conversation handling became more resilient and better instrumented.",
    items: [
      {
        title: "Buffered agent invocation",
        description:
          "Agent responses can be buffered through a stronger invocation path for dashboard and automation usage.",
        category: "new",
      },
      {
        title: "Tool call tracing",
        description:
          "Tool calls are recorded in conversation history to make agent activity easier to inspect.",
        category: "improved",
      },
      {
        title: "Refresh token flow",
        description:
          "Sign-in stability improved with refresh token handling and a clearer re-authentication timeout.",
        category: "fixed",
      },
      {
        title: "Prompt templating",
        description:
          "Prompt construction now supports Jinja templates for cleaner prompt composition.",
        category: "developer",
      },
    ],
  },
  {
    date: "2026-05-08",
    title: "Gmail skill",
    summary:
      "Gmail became available as a skill for email workflows.",
    items: [
      {
        title: "Gmail actions",
        description:
          "Agents can search, read, archive, delete, mark, and batch-delete Gmail messages when the connector is authorized.",
        category: "new",
      },
    ],
  },
  {
    date: "2026-05-03",
    title: "Developer tooling improvements",
    summary:
      "Early developer workflow support was added.",
    items: [
      {
        title: "VS Code plugin",
        description:
          "A VS Code plugin was added for pair-programming workflows.",
        category: "new",
      },
      {
        title: "Global key state",
        description:
          "Key state handling was centralized for smoother app behavior.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-05-01",
    title: "Branding polish",
    summary:
      "Launch-facing polish continued across the app shell.",
    items: [
      {
        title: "Browser tab logo",
        description:
          "The browser tab now uses the InnoMight Labs logo.",
        category: "improved",
      },
      {
        title: "Widget input update",
        description:
          "The widget API no longer applies the previous input cap.",
        category: "improved",
      },
    ],
  },
];
