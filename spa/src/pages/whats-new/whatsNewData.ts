export type ChangeCategory = "new" | "improved" | "fixed";

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
    date: "2026-10-10",
    title: "Build with Ada, and kits",
    summary:
      "Ada, InnomightLabs' solution builder, sets up what you describe in a chat: agents, knowledge bases, skills, tools and chat widgets. Everything she builds is kept together as a kit you can change, roll back or remove as one.",
    items: [
      {
        title: "Build with Ada",
        description:
          "Tell Ada what you need, or pick one of her ideas, such as a website support agent, a lead qualifier with email alerts, a web research team or a report studio. She shows you a drawing of the plan and builds only when you approve it.",
        category: "new",
      },
      {
        title: "Kits",
        description:
          "Everything one build creates is a kit, listed on the Build with Ada page with what it holds. Each change you approve is a new version, and Ada only ever changes or removes what the kit itself built, never the things you added yourself.",
        category: "new",
      },
      {
        title: "Roll back a kit to any version",
        description:
          "Open a kit to see its versions and go back to any of them. You see exactly what will change before anything happens, including anything you edited in the dashboard, which is kept as you left it.",
        category: "new",
      },
      {
        title: "Remove a kit and everything in it",
        description:
          "One action deletes a kit's agents, knowledge bases and chat widgets together, after showing you the full list. Connections to other services stay on your account.",
        category: "new",
      },
      {
        title: "Ada asks only what you know",
        description:
          "When a skill needs something only you can tell her, such as where lead emails should go, the chat shows a short form for it. Ada writes the rest of the setup herself.",
        category: "new",
      },
      {
        title: "Web search for your agents",
        description:
          "Agents can search and read the web through Tavily. Ada asks you to connect it from a card in the chat, and you sign in once for every agent that uses it.",
        category: "new",
      },
      {
        title: "Changes that finish or put everything back",
        description:
          "If a build fails part-way, or the server restarts in the middle of one, everything it had done is undone, so you're never left with half a solution.",
        category: "improved",
      },
      {
        title: "Ada's conversations stay on her page",
        description:
          "Building with Ada no longer fills your conversations list; her conversations are on the Build with Ada page.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-10-06",
    title: "Public API, embeddable widget, and MCP sharing",
    summary:
      "Agents can now be reached from your own apps and sites through a public API and an iframe widget, and you can let those outside users call selected MCP tools on your behalf.",
    items: [
      {
        title: "Public API with secret keys",
        description:
          "Generate sk_live_ secret keys for an agent and chat with it through the versioned /v1 API, with the same skills, knowledge bases, and tools it has in the dashboard. Each key is scoped to one agent and its usage is tracked.",
        category: "new",
      },
      {
        title: "Embeddable iframe widget",
        description:
          "A new chat widget that runs in an iframe on any site, set up with a small loader script and data attributes. The existing widget keeps working alongside it.",
        category: "new",
      },
      {
        title: "Per-user conversations and conversation context",
        description:
          "API clients get a separate conversation for each of their end users, and a conversation can carry a context attribute that tells the agent what it is about.",
        category: "new",
      },
      {
        title: "MCP sharing for widget, A2A, and API users",
        description:
          "Share an agent's MCP connector with widget visitors, Agent2Agent callers, and API keys, one connector at a time, choosing exactly which tools they may call. Sharing only starts after you accept that they act through your connected account.",
        category: "new",
      },
      {
        title: "Automations guide",
        description:
          "A new Automations page in the docs walks through building a daily briefing email, using live examples of the real automation editor.",
        category: "new",
      },
      {
        title: "Safer marketplace publishing",
        description:
          "Published automation templates no longer include your skill settings, such as email recipients. Invoke Agent steps now ask whoever imports the template to choose one of their own agents.",
        category: "improved",
      },
      {
        title: "Stronger sign-in and token handling",
        description:
          "OAuth and token handling for the dashboard, widget, and Agent2Agent was rewritten to be more secure.",
        category: "improved",
      },
      {
        title: "More dependable agent runs",
        description:
          "The agent loop now always ends with an answer or a record of what ran. Long Codex tool runs keep their final answer, and background tool jobs report failures correctly.",
        category: "fixed",
      },
      {
        title: "Automation step checks",
        description:
          "An Invoke Agent step with no agent chosen is now caught before activation or a test run, instead of failing mid-run.",
        category: "fixed",
      },
    ],
  },
  {
    date: "2026-09-27",
    title: "MCP provider catalog and Google Ads",
    summary:
      "Connect popular MCP providers from a curated catalog, run hosted MCP servers without managing them yourself, and manage Google Ads from your agents.",
    items: [
      {
        title: "MCP provider catalog",
        description:
          "The Connectors page now offers ready-made MCP providers, starting with Atlassian, GitHub, Canva, and Google Ads. Install them from a short form, or in one click where the provider supports it.",
        category: "new",
      },
      {
        title: "Hosted stdio MCP servers",
        description:
          "MCP servers that normally run as local processes are now hosted for you, so they can be connected like any other connector.",
        category: "new",
      },
      {
        title: "Google Ads skill",
        description:
          "Agents can work with your Google Ads account for SEO and campaign management. A Google Ads developer token is no longer needed.",
        category: "new",
      },
      {
        title: "Messages no longer vanish after streaming",
        description:
          "Fixed an issue where the agent's reply could disappear once streaming finished, and tool results are now matched to the right call.",
        category: "fixed",
      },
    ],
  },
  {
    date: "2026-09-19",
    title: "Background conversations, agent dreams, and a new automation editor",
    summary:
      "Conversations now run in the background so you can work on several at once, agents can tidy their memory overnight, and automations are built in one simpler workspace.",
    items: [
      {
        title: "Background conversations",
        description:
          "Each conversation turn runs as a background job, so replies keep going if you leave the page and you can work in several conversations at once.",
        category: "new",
      },
      {
        title: "Agent dreams",
        description:
          "MemGPT agents can run a nightly dream that replays the day's conversations and organizes their memory: keeping what lasts, correcting what changed, and removing what is stale. Configure it in Settings.",
        category: "new",
      },
      {
        title: "Redesigned automation workspace",
        description:
          "Automations are now built as a simple top-to-bottom chain of triggers and steps, with testing, run history, and analytics on the same screen.",
        category: "improved",
      },
      {
        title: "Ollama provider",
        description: "Run agents on your own self-hosted Ollama models.",
        category: "new",
      },
      {
        title: "Default agent",
        description: "Choose a default agent in Settings so new conversations start with it selected.",
        category: "new",
      },
      {
        title: "Clearer agent activity",
        description: "The agent activity view now shows which tool is being called.",
        category: "improved",
      },
      {
        title: "Lighter automation storage",
        description:
          "Automation runs store each result once and leave out bulky event data, roughly halving their storage.",
        category: "improved",
      },
      {
        title: "Better results from smaller models",
        description:
          "Responses from smaller models are parsed more reliably, and WordPress image results now always work in the editor.",
        category: "fixed",
      },
    ],
  },
  {
    date: "2026-09-08",
    title: "New skills, canvas visuals, and token usage",
    summary:
      "Agents gained skills for the AWS CLI, Python, and files, can draw rich visuals on a canvas, and every conversation now shows how many tokens it uses.",
    items: [
      {
        title: "AWS CLI skill",
        description:
          "Agents can run AWS CLI commands through an isolated runner, limited by a policy you set. Smart suggestions can help write the policy.",
        category: "new",
      },
      {
        title: "Python execution skill",
        description: "Agents can run Python code in a controlled environment to calculate and analyze.",
        category: "new",
      },
      {
        title: "File manager skill",
        description: "Agents can create, read, and organize files.",
        category: "new",
      },
      {
        title: "HTML canvas",
        description:
          "Agents can render complex visuals as HTML, shown inline in the chat and in a side panel.",
        category: "new",
      },
      {
        title: "Token usage analytics",
        description:
          "Conversations show token usage, updated with every message, and the overview page includes usage analytics.",
        category: "new",
      },
      {
        title: "Tool call timeline",
        description:
          "Agent tool calls are shown as a compact timeline in the chat, and the agent skills page was redesigned.",
        category: "improved",
      },
      {
        title: "Smart suggestions for agent instructions",
        description: "Smart suggestions can now help write an agent's instructions.",
        category: "improved",
      },
      {
        title: "Agent2Agent OAuth 2.1",
        description:
          "Agent2Agent clients can register themselves through dynamic client registration and authenticate with OAuth 2.1.",
        category: "new",
      },
      {
        title: "Resumable knowledge base jobs",
        description:
          "A failed knowledge base crawl can be retried and resumes from the page it reached.",
        category: "improved",
      },
      {
        title: "Retry on empty replies",
        description: "If an agent returns no response, it is retried once automatically.",
        category: "fixed",
      },
      {
        title: "Updated privacy, terms, and pricing policies",
        description: "The privacy policy, terms, and pricing policy were rewritten and expanded.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-08-23",
    title: "Gemini models and Agent2Agent upgrades",
    summary:
      "Agents can now use Google Gemini models, model selection is easier to search, and Agent2Agent workflows have richer discovery, trust controls, and debugging views.",
    items: [
      {
        title: "Google Gemini provider",
        description:
          "Users can configure a Gemini API key, select Gemini models loaded from Google's model list, and run agents through the shared LLM provider interface.",
        category: "new",
      },
      {
        title: "Searchable model selection",
        description:
          "Agent and smart-suggestion model fields now use a searchable select so long provider model lists are easier to scan and choose from.",
        category: "improved",
      },
      {
        title: "Agent2Agent protocol support",
        description:
          "Agents can be exposed through Agent2Agent endpoints, invoked with authenticated API keys, and discovered through public agent cards and registry listings.",
        category: "new",
      },
      {
        title: "Agent2Agent trust controls",
        description:
          "Workspace settings now let users allowlist trusted Agent2Agent origins before installing or invoking remote agents through the Agent2Agent client skill.",
        category: "new",
      },
      {
        title: "Agent2Agent analytics and debugging",
        description:
          "Agent detail pages now include Agent2Agent task history and debugging views so owners can inspect inbound A2A activity per agent.",
        category: "new",
      },
      {
        title: "Dashboard and agent overview polish",
        description:
          "The dashboard overview and agent overview pages were redesigned with clearer information hierarchy, updated theme tokens, and more consistent controls.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-07-02",
    title: "A more consistent dashboard",
    summary:
      "Spacing, buttons, forms, and cards now look the same across the whole dashboard.",
    items: [
      {
        title: "Consistent page layouts",
        description:
          "Dashboard pages share one layout, so margins and card spacing are the same everywhere.",
        category: "improved",
      },
      {
        title: "Button and form consistency",
        description:
          "Buttons and form fields are sized and spaced the same way on every page.",
        category: "improved",
      },
      {
        title: "Faster route loading",
        description:
          "Pages load only when you open them, so the site starts faster.",
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
          "Slow skill actions run in the background, with their progress, result, or error kept until the agent picks them up.",
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
          "Report generation and other slow tool calls are much less likely to time out.",
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
          "Automation trigger lists load faster.",
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
        title: "Scheduled automations",
        description:
          "Automations can be scheduled to run by themselves at planned times.",
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
          "Supported skills can be used directly as automation steps.",
        category: "new",
      },
      {
        title: "Sub-agent invocation support",
        description:
          "Agents can hand work to your other agents as sub-agents, with each call starting fresh.",
        category: "new",
      },
    ],
  },
  {
    date: "2026-05-30",
    title: "WordPress connector and pricing updates",
    summary:
      "A WordPress connector arrived and pricing was simplified.",
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
          "Pricing was simplified.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-05-25",
    title: "Widget polish and image streaming",
    summary:
      "The website widget got a refresh, and image generation can now stream its results.",
    items: [
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
          "Plugins can be downloaded from the Downloads page.",
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
        title: "More reliable agent replies",
        description:
          "Agents answer more reliably in the dashboard and in automations.",
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
    title: "VS Code plugin",
    summary:
      "Pair-program with your agents from inside VS Code.",
    items: [
      {
        title: "VS Code plugin",
        description:
          "A VS Code plugin was added for pair-programming workflows.",
        category: "new",
      },
    ],
  },
  {
    date: "2026-05-01",
    title: "Branding polish",
    summary:
      "Small touches across the app.",
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
          "Visitors can send longer messages through the widget.",
        category: "improved",
      },
    ],
  },
];

/** One anchor per month, on that month's newest release, e.g. `#2026-10`. */
export const releaseMonths: { id: string; label: string }[] = changeLogEntries
  .map((entry) => entry.date.slice(0, 7))
  .filter((month, index, months) => months.indexOf(month) === index)
  .map((month) => ({
    id: month,
    label: new Intl.DateTimeFormat("en", { month: "long", year: "numeric" }).format(
      new Date(`${month}-01T00:00:00Z`)
    ),
  }));

export function monthAnchor(entry: ChangeLogEntry, index: number): string | undefined {
  const month = entry.date.slice(0, 7);
  const previous = changeLogEntries[index - 1];
  return previous?.date.startsWith(month) ? undefined : month;
}

export const totalChanges = changeLogEntries.reduce((count, entry) => count + entry.items.length, 0);
