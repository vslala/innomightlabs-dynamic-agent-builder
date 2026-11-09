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
    date: "2026-11-09",
    title: "See every tool call an automation's agent made, in order",
    summary:
      "Each automation run has its own phone-first inspector page: every step the run took and every tool call its agents made, in the order they made them, with the real tool, full arguments, full response, start time and duration. Nothing is cut short. This is built and tested; deployment and manual checks on real runs are still pending.",
    items: [
      {
        title: "A dedicated page for each automation run",
        description:
          "Open a run from the Runs drawer in an automation's workspace, or follow \"Inspect N tool calls\" on a step card, to reach /dashboard/automations/<automation id>/runs/<run id>. The top of the page summarises the run: status, error, duration, how many steps passed, how many tool calls were made and what triggered it. Below that are the steps the run took; pick one to see its Activity, Output, Input and Raw tabs. The page is laid out for phones first: one column, sticky tabs, and a tool call opens in a bottom sheet with previous and next buttons. On wider screens the summary and steps become a left column and a call opens in a side pane. The run page refreshes while the run is still executing. The inspector is built and tested; deployment and manual checks on real runs are still pending.",
        category: "new",
      },
      {
        title: "An agent step's activity as a timeline",
        description:
          "The Activity tab reads like what the agent did: the prompt it was given, then each tool call numbered in order (title, tool name, a one-line summary of its arguments, its duration, and its status if it didn't succeed), then the agent's reply. Search the calls, or filter them by All, Failed, No result, or a single tool, to find the call that went wrong in a long run. Calls made through a connected MCP server show the actual MCP tool and its arguments, not a generic \"Call MCP tool\".",
        category: "new",
      },
      {
        title: "Full responses, and links to a single call",
        description:
          "Tool responses are kept whole. Before, each recorded response was cut at 16,000 characters. Long text folds behind \"Show all · N characters\", and the full value is always one tap away. The page address records the selected step, tab and call (?step=<result id>&tab=activity|output|input|raw&call=<tool call id>), so you can share a link that opens straight to one tool call.",
        category: "improved",
      },
      {
        title: "Tool results matched to the right call, with real timings",
        description:
          "When an agent called the same tool several times in one step, such as reading three pages, a result could be shown against another call's arguments, and calls were listed when their result arrived rather than when they were made. Each result is now matched to its own call by id and listed in the agent's order. Durations measure the tool's own run, so calls requested together no longer look slower than they were. Runs recorded before this change still open in the inspector, without timings.",
        category: "fixed",
      },
      {
        title: "Tool events are no longer part of a step's output",
        description:
          "A step's tool-call events are kept in their own log and shown in the inspector, so they are no longer in the step's output or the run's context. A smart value that read them, such as {{ steps.draft.output.events.0.content }}, no longer resolves; read the step's documented outputs instead. While an agent step is still running, its tool calls appear only once the step finishes.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-11-09",
    title: "Ila can add and remove an agent's memory blocks",
    summary:
      "When Ila builds or updates an agent, she can give it custom core memory blocks besides human and persona, such as a block for your projects or follow-ups, and remove them later. Blocks go into your own memory with that agent, exactly as the agent's Memory page adds them, so memory stays per person. Like every change Ila makes, they appear in the plan and apply only after you approve. This is built and tested; checks in a live Ila session are still pending.",
    items: [
      {
        title: "Ask Ila for memory blocks on an agent",
        description:
          "Tell Ila what an agent should keep track of, for example \"remember my open projects and their deadlines\". She adds a memory block to the agent's blueprint with a name (lowercase with underscores, such as projects), a description the agent reads to decide what belongs there, and a word limit (100 to 50,000, 5,000 by default). The agent keeps the block in its prompt every turn and edits it with its memory tools. The plan shows \"add memory block projects\", and changing a block's description or word limit shows \"update memory block projects\" and keeps what it already holds. The blocks appear on the agent's Memory page (Dashboard → Agents → the agent → Memory). Built and tested; checks in a live Ila session are still pending.",
        category: "new",
      },
      {
        title: "Remove a memory block through Ila",
        description:
          "Ask Ila to drop a block and she takes it out of the agent's blueprint. The plan lists \"remove memory block projects and what it holds\" separately, because deleting a block also deletes its content and can't be undone. It runs only after everything that can be undone has succeeded. Blocks you added yourself on the Memory page show up in Ila's view of the agent, and she removes one only when you ask, with the removal listed in the plan. The human and persona blocks every agent has can't be added or removed this way.",
        category: "new",
      },
      {
        title: "Memory stays per person",
        description:
          "A block Ila adds belongs to your memory with the agent: what the agent remembers there with you, nobody else sees. People who chat with the agent through a widget, as a guest or through the API keep only the human and persona blocks, so use an agent's instructions or a knowledge base for facts every visitor should get. If you haven't chatted with the agent yet, adding a block also sets up your human and persona blocks, so you never end up without them.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-11-04",
    title: "Agents can work through much longer tasks",
    summary:
      "A single agent turn can now run far longer before it stops: up to 200 model calls instead of 37, and up to two hours of waiting on each long-running tool job instead of ten minutes. Long research, report building and multi-step automations finish in one turn instead of stopping partway.",
    items: [
      {
        title: "Up to 200 model calls in one turn",
        description:
          "An agent's turn may call the model up to 200 times, up from 37, using tools between calls. If it still needs to go on after the last call, the agent makes one extra call with tools switched off to sum up what it has done, so you always get an answer rather than a turn that just stops. The budget counts model calls, not individual tools (one call can request several) and not conversation messages. Longer turns can use more provider tokens and cost more on your provider account.",
        category: "improved",
      },
      {
        title: "Long-running tools get up to two hours",
        description:
          "When a tool runs as a background job, the agent now waits up to 120 minutes for each job, up from 10, checking every two seconds. Waiting doesn't use up the turn's model calls. Chat turns keep running on the server, so you can close the page and come back to the conversation, which picks the reply up where it is. Tool and provider time limits and stuck-job detection are unchanged.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-11-03",
    title: "Shared accounts use the owner's plan, and clearer limit messages",
    summary:
      "In a shared account, what members do now counts against the account owner's plan instead of each member's own, so a member on the free tier can build in an account the owner pays for. Reaching a limit now says which limit and why, Leads works on phones, and Ila's chat no longer gets stuck after you submit a form.",
    items: [
      {
        title: "A shared account's usage is billed to its owner",
        description:
          "Agents, chat messages and crawled knowledge-base pages in a shared account are checked against and counted for the account owner: their plan, their usage and any unlimited access they have. Before, a member's own free plan could stop them creating even a first agent in an account the owner pays for. The agent limit counts every agent in every account the owner owns, whoever created it. A member's personal account is still billed to that member. Crawled pages are now counted reliably; before, page usage was recorded against the wrong id and wasn't counted.",
        category: "improved",
      },
      {
        title: "Limit refusals say what happened",
        description:
          "Reaching a plan limit used to surface as a generic server error. The API now answers 429 with the reason (which limit was reached), and creating an agent shows that reason, or explains a missing permission (\"Ask an account administrator for access\") or a network failure, instead of \"Failed to create agent\". The message is announced to screen readers.",
        category: "fixed",
      },
      {
        title: "Leads on phones",
        description:
          "Dashboard → Leads is laid out for small screens: the captures list fills the screen, opening a capture shows its details on their own with a \"Back to leads\" button, and going back returns you to the capture you opened. Answers, attachments and long file names wrap instead of overflowing, and keyboard focus moves to the capture's heading when it opens.",
        category: "improved",
      },
      {
        title: "Ila's chat no longer stalls after a form",
        description:
          "After you submitted a form in Ila's chat, such as a skill's settings, a sticky \"Captured … Processing...\" line stayed on screen and the message box stayed disabled until the page reloaded. That line is gone, and the message box stays usable while Ila works on your answer.",
        category: "fixed",
      },
    ],
  },
  {
    date: "2026-11-02",
    title: "Social publishing support for Facebook Pages, Instagram and Threads",
    summary:
      "The Social media skill adds support for publishing to Facebook Pages, Instagram professional accounts and Threads, alongside the existing LinkedIn connections. Connectors appear when their sign-in integration is configured; Instagram and Threads manual checks and Meta App Review are still pending, so this is not an announcement of unrestricted availability.",
    items: [
      {
        title: "Publish to the Facebook Pages you manage",
        description:
          "In Dashboard → Connectors → Social, choose Facebook Pages and select the Pages you want to connect during Facebook sign-in. An agent with the Social media skill can publish a text post or a post with up to 10 still images to selected Pages, with a preview before publishing unless you have already allowed that action. One sign-in can connect multiple Pages. This connector publishes as a Page, not as your personal Facebook profile, and requires Page access that permits creating content. Connector support is implemented; availability depends on the configured Facebook integration and Meta App Review, which is still pending.",
        category: "new",
      },
      {
        title: "Instagram image posts and carousels for professional accounts",
        description:
          "The Instagram connector supports Business and Creator accounts linked to a Facebook Page. Connect through Facebook sign-in from Connectors → Social, sharing the Page linked to your Instagram account. Agents can prepare a caption and publish one still image or a carousel of up to 10 images; Instagram requires an image and supports captions up to 2,200 characters. Personal accounts, Reels, Stories and video publishing are not supported by this connector. Instagram manual checks and Meta App Review are still pending; this is implemented support, not confirmed general availability.",
        category: "new",
      },
      {
        title: "Threads text posts and image carousels",
        description:
          "Connect your Threads profile through its own sign-in in Connectors → Social. The Social media skill can publish text-only posts, text with one still image, or carousels of up to 20 images, within the connector's 500-character limit. Use it to adapt an announcement for Threads without copying it from another network by hand. The connector does not yet publish videos, replies, quote posts or polls. Threads manual checks and Meta App Review are still pending; this is implemented support, not confirmed general availability.",
        category: "new",
      },
      {
        title: "Check recent posts before drafting the next one",
        description:
          "Agents can read recent posts from connected Facebook Pages, Instagram accounts and Threads profiles, including their text, timestamps and post links. Ask an agent to review what you have already published before drafting a follow-up or planning the next announcement, helping it avoid repeating the same message. This reads your connected identities' own posts, not a general social feed; LinkedIn recent-post reading is not supported.",
        category: "new",
      },
      {
        title: "Prepare one announcement for different social networks",
        description:
          "Use the Social media skill to check a draft against each selected account's posting limits and provide different wording for each network. Images from the conversation, generated images and saved image artifacts are prepared for each destination; Instagram images outside its supported proportions are padded rather than cropped. Publishing reports success or failure separately for each account, with a post link where the network returns one, so a failed destination is not mistaken for a successful cross-post.",
        category: "improved",
      },
      {
        title: "Social sign-in explains why no accounts were connected",
        description:
          "If social sign-in completes without connecting an eligible account, the Social tab now explains the next step: select the right Facebook Pages, enable the requested permissions, obtain a Page role that can publish, or link an Instagram Business or Creator account. Facebook Page discovery also handles Pages accessed through Business portfolios when Facebook omits role details. Missing permissions in InnomightLabs' own Facebook app configuration are identified as a setup issue rather than blamed on your account.",
        category: "fixed",
      },
    ],
  },
  {
    date: "2026-11-02",
    title: "Understand and manage each member's account permissions",
    summary:
      "A dedicated member permissions page shows what a teammate can do in each service, which policies grant that access, and where restrictions apply. Authorized administrators can add or remove policies without treating account administration as blanket access to everyone's content.",
    items: [
      {
        title: "See access by service, not just a list of policy names",
        description:
          "Open a member from Dashboard → IAM → Members to inspect their permissions. The Access by service table summarizes full, limited or no policy access in each part of InnomightLabs and lists the allowed, conditional and denied actions. The page also shows which policies apply and whether they come from the member or a group, making it easier to explain why a teammate can or cannot perform an action. Resources shared directly with that person can provide additional access beyond this policy summary.",
        category: "new",
      },
      {
        title: "Attach or remove built-in and custom policies",
        description:
          "Administrators with permission to manage member access can attach an existing built-in or custom policy, or remove a directly attached policy, from the member's permissions page. Changes apply on the member's next request. People with view-only permission can inspect access without changing it, and the account owner's full access cannot be removed. An explicit Deny takes precedence over an Allow, so attaching another policy does not silently bypass a restriction.",
        category: "new",
      },
      {
        title: "Clearer separation between account administration and private content",
        description:
          "Built-in role descriptions now explain the difference between managing the account and reading other people's work. AdministratorAccess covers members, permissions, billing, settings and resource administration, but does not by itself grant access to other members' private conversation or knowledge-base content. Content access still depends on ownership or sharing. This makes it easier to delegate account operations without assuming an administrator should see everything a teammate creates.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-11-01",
    title: "Simpler plans, with every feature in each one",
    summary:
      "Free, Business and Growth are the three standard plans, with Enterprise available for custom requirements. Standard plans share the platform's features and differ in usage allowances and support. Bring your own AI provider credentials: model usage is billed separately by your provider, not included in the subscription.",
    items: [
      {
        title: "Business and Growth replace Starter and Pro",
        description:
          "Business costs £49 per month and includes 5 agents, 10,000 messages per month, 500 knowledge-base pages, 10 lead forms and 1,000 lead captures per month, with unlimited memory and email support. Growth costs £149 per month and includes 20 agents, 50,000 messages, 5,000 knowledge-base pages, unlimited lead forms and 10,000 lead captures per month, with unlimited memory, priority support and an onboarding call. Annual billing is £490 for Business or £1,490 for Growth, equivalent to two months free.",
        category: "new",
      },
      {
        title: "Done-with-you setup",
        description:
          "A separate £499 one-off setup service helps you launch your first working solution: we build it with you, connect it to your website and tools, and walk your team through running it. This is optional hands-on implementation help, not a recurring subscription charge or an AI-usage allowance.",
        category: "new",
      },
      {
        title: "A clearer pricing page",
        description:
          "Compare subscription prices, usage allowances and support side by side. Free remains £0 with 1 agent, 100 messages per month and 10 knowledge-base pages, while Enterprise offers custom limits, invoicing, a named contact and help with security reviews. The page distinguishes the platform subscription from AI-provider charges so you can estimate both costs before choosing a plan.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-11-01",
    title: "More predictable provider setup and safer API calls",
    summary:
      "Model choices now reflect the AI providers your account has actually configured, LinkedIn Pages sign-in requests the correct permissions, and REST Template calls use public domain names rather than raw IP addresses.",
    items: [
      {
        title: "Bedrock uses your account's configured AWS credentials",
        description:
          "Amazon Bedrock is offered in agent model selection only after your account configures it, matching the behavior of other AI providers. Model discovery and agent requests use your saved AWS credentials rather than falling back to the server's AWS identity. This keeps model selection tied to your own provider setup and avoids offering Bedrock as though it were already included or configured for every account.",
        category: "fixed",
      },
      {
        title: "Corrected LinkedIn Pages sign-in permissions",
        description:
          "Connecting LinkedIn Pages now requests the authorization scopes expected by the Pages integration, fixing a permission mismatch that could stop sign-in before it completed. This improves connecting company Pages you administer; it does not introduce a new LinkedIn connector or add LinkedIn feed-reading capabilities.",
        category: "fixed",
      },
      {
        title: "REST templates call public services by domain name",
        description:
          "REST Template requests and every redirect must use a domain name, not a raw IPv4 or IPv6 address, and cannot override the destination through a different Host header. Private and internal network destinations remain blocked. Public InnomightLabs endpoints are allowed, so a template can call an automation webhook by its public domain. If an existing template uses a numeric IP address, replace it with the service's public domain name before running it again.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-10-31",
    title: "A conversation workspace designed for phones",
    summary:
      "The web dashboard is easier to use on a small screen, with a mobile-first conversation layout, touch-friendly controls and better recovery when you return to a chat. These improvements apply to the website; the iOS and Android app shells are development groundwork, not an App Store or Google Play launch.",
    items: [
      {
        title: "Chat and work with attachments on a smaller screen",
        description:
          "The conversation workspace, message composer, attachment controls and canvas panel now adapt to phone-sized screens. Menus and actions are available without relying on a mouse hover, touch targets are larger, and dialogs open as bottom sheets on phones. This makes it easier to send a message, manage attached files and inspect an agent's output without needing the desktop layout.",
        category: "improved",
      },
      {
        title: "Catch up when you return to a conversation",
        description:
          "When you bring the browser tab or app back to the foreground, the conversation resynchronizes with the server so work completed while you were away appears in the chat. Requests also attempt a session refresh and retry once when authentication expires, reducing interruptions caused by a stale access token. This is recovery for an online session, not offline chat support.",
        category: "improved",
      },
      {
        title: "Delete your account from Settings",
        description:
          "Settings now includes a Delete account action with an email-confirmation step. Confirming permanently deletes the account and its agents, conversations, knowledge bases, automations and connections, and cancels an active subscription. Access is disabled immediately while the remaining deletion runs in the background. This is an irreversible account deletion, not a way to leave a single conversation or remove one agent.",
        category: "new",
      },
      {
        title: "Continue choosing a subscription after signing in",
        description:
          "If you choose a paid plan while signed out, the website preserves the pending checkout and resumes it after login. You no longer need to return to the pricing page and select the same plan again just because authentication interrupted the purchase flow.",
        category: "fixed",
      },
    ],
  },
  {
    date: "2026-10-26",
    title: "Approve what your agents do for you",
    summary:
      "Before an agent posts, sends an email or runs a tool that changes things, it shows you exactly what it will do. Approve it, edit it, reject it, or always allow it.",
    items: [
      {
        title: "Approval cards in chat",
        description:
          "For actions that require consent, such as social publishing and sending Gmail, the agent pauses and shows an approval card in the conversation before carrying out the action. The preview includes the relevant text, images, recipients or destination accounts. Approve the proposed action, edit supported fields, or reject it with a reason; the agent continues from that decision instead of treating a rejected action as completed. This lets you review work that leaves the chat before it is posted or sent.",
        category: "new",
      },
      {
        title: "Always allow",
        description:
          "For actions you trust an agent to carry out, choose Always allow when approving the action. That agent can then run the action without repeated approval prompts in chat and scheduled work. Review or revoke this choice on the agent's Skills or MCP Tools page whenever your needs change. This is an explicit permission you grant for an action, not a switch that automatically authorizes every tool the agent can use.",
        category: "new",
      },
      {
        title: "Automations ask once, when you build them",
        description:
          "Automation steps that need consent ask for it during setup, whether you build the workflow in the editor or through Ila's chat. Once approved, the step can run unattended on its schedule; changing the step requires approval again. Existing automations that publish posts or send email may need attention: open the workflow and approve the affected step so it can continue running. This moves the review to setup rather than leaving a scheduled job waiting for a live chat response.",
        category: "improved",
      },
      {
        title: "MCP tools that ask first",
        description:
          "MCP tools that their server marks as destructive now request approval before execution. In the connector's settings, choose which tools should ask for consent, then manage an agent's Always allow choices from its MCP Tools page. This extends the review flow to connected tool servers; it does not mean every MCP action is automatically classified as destructive or that every tool always prompts.",
        category: "new",
      },
    ],
  },
  {
    date: "2026-10-25",
    title: "Documents in chats and knowledge bases",
    summary:
      "Attach PDFs, Word files, slides, spreadsheets and scans to a chat or a knowledge base. They are read in the background, and agents read just the part they need instead of the whole file.",
    items: [
      {
        title: "Attach documents in chat",
        description:
          "Add a PDF, Word file, slides, a spreadsheet or a scan next to your message. It is read in the background and shows on your message as a chip. The agent knows the file arrived, in this chat and when you open the conversation again, so you don't have to point it there.",
        category: "new",
      },
      {
        title: "Upload files to a knowledge base",
        description:
          "Upload the same kinds of files to a knowledge base. Each shows its progress, can be retried if reading failed, and is removed together with what it added to search when you delete it.",
        category: "new",
      },
      {
        title: "Agents read large files in parts",
        description:
          "Agents see a file's sections, tables and pages first, then read only what the question needs. For a spreadsheet they can filter, group and total thousands of rows without reading them, so questions like \"how many runs did Madawa score\" are answered from every row.",
        category: "new",
      },
      {
        title: "Scans and layouts",
        description:
          "Scanned pages are read with OCR, payslips and statements keep their tables, and an agent can look at a page as an image to check amounts, stamps or signatures.",
        category: "new",
      },
      {
        title: "Knowledge base reading view shows Markdown",
        description:
          "A page's reading view now shows headings, lists and tables as they are meant to look, instead of raw text.",
        category: "fixed",
      },
    ],
  },
  {
    date: "2026-10-24",
    title: "WordPress search, Drive and Gmail writes",
    summary:
      "The WordPress AI Search plugin is available, and agents can now write to Google Drive and Gmail, not only read.",
    items: [
      {
        title: "WordPress AI Search plugin",
        description:
          "Add an InnomightLabs search box to a WordPress site. Agents can read a post's full content with the WordPress Search skill when a snippet isn't enough.",
        category: "new",
      },
      {
        title: "Write to Google Drive",
        description:
          "Agents can create and update files in your Google Drive once you have authorized the connector.",
        category: "new",
      },
      {
        title: "Draft and send Gmail",
        description:
          "Agents can write email drafts and send messages from your Gmail account, in chats and in automations.",
        category: "new",
      },
      {
        title: "Share REST templates safely",
        description:
          "REST Template skills can be shared with others, with safeguards on where they are allowed to send requests.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-10-22",
    title: "Agents that make site videos",
    summary:
      "A new Browser Studio skill lets agents look at websites, record walkthroughs and turn them into finished videos.",
    items: [
      {
        title: "Inspect and record sites",
        description:
          "Agents can open a public site, take screenshots, rehearse a walkthrough step by step and record it.",
        category: "new",
      },
      {
        title: "Compose a video",
        description:
          "Clips, zooms, transitions, text overlays and a music bed are joined into one MP4 you can play right in the conversation.",
        category: "new",
      },
      {
        title: "Videos as artifacts",
        description:
          "A video from the conversation workspace can be saved as an artifact, and idle workspaces are cleaned up on their own.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-10-21",
    title: "Social accounts, more connectors and named skills",
    summary:
      "Connect LinkedIn and publish to it from an agent. The Connectors page has more ready-made providers, and every skill you install can have its own name.",
    items: [
      {
        title: "Social tab and LinkedIn",
        description:
          "Connect LinkedIn from the new Social tab on the Connectors page. Agents with the Social Media skill can check your account and publish text posts, with one or several images.",
        category: "new",
      },
      {
        title: "Searchable connector catalog",
        description:
          "The Connectors page has search and brand icons, and five more ready-made providers, including Exa, DeepWiki, Hugging Face, Microsoft Learn and Context7.",
        category: "new",
      },
      {
        title: "Name each skill you install",
        description:
          "When you install a skill you can give it a title and a description, which is what the agent reads. Install the same skill twice for different jobs and tell the copies apart.",
        category: "new",
      },
      {
        title: "Scheduled automation runs",
        description:
          "A scheduled automation run now starts at its own schedule trigger.",
        category: "fixed",
      },
    ],
  },
  {
    date: "2026-10-18",
    title: "Fresher knowledge bases and diagrams in chat",
    summary:
      "Knowledge bases keep up with their sites without re-reading everything, and Mermaid diagrams appear as pictures in chats.",
    items: [
      {
        title: "Re-crawls update only what changed",
        description:
          "Reading a site again only re-embeds the pages that changed, and pages the site no longer serves are removed from search, so answers don't quote stale content.",
        category: "improved",
      },
      {
        title: "Recrawl on a schedule",
        description:
          "The Knowledge Base skill reads a knowledge base's site again, so an automation can keep it up to date on a schedule.",
        category: "new",
      },
      {
        title: "Page by page view of a knowledge base",
        description:
          "Open a page of a knowledge base to see its chunks as search sees them, a map of how they are sized, and a reading view.",
        category: "new",
      },
      {
        title: "Pages that load with JavaScript",
        description:
          "Sites that build their pages in the browser are now rendered before they are read, instead of coming back empty.",
        category: "improved",
      },
      {
        title: "Mermaid diagrams in chat",
        description:
          "Diagrams an agent writes in Mermaid show as pictures in the dashboard chat and the embedded widget.",
        category: "new",
      },
      {
        title: "Deleting a knowledge base is all or nothing",
        description:
          "Its vectors are removed first. If that fails, nothing else is deleted, so you can try again without leaving anything half removed.",
        category: "fixed",
      },
    ],
  },
  {
    date: "2026-10-15",
    title: "Leads",
    summary:
      "Agents can collect leads for you: you define a form, the agent fills it in over the conversation, and every captured lead can start an automation.",
    items: [
      {
        title: "Lead forms and captures",
        description:
          "Define what you want to know about a visitor. The agent asks naturally, remembers what it learned across visits, and saves the lead once the form is complete. The same lead is never saved twice.",
        category: "new",
      },
      {
        title: "Leads dashboard",
        description:
          "Browse leads by agent, form, status and date, edit forms, set statuses and see your usage.",
        category: "new",
      },
      {
        title: "Start automations from a lead",
        description:
          "A new Lead captured trigger starts an automation, so leads can go to email, a CRM or any other action.",
        category: "new",
      },
      {
        title: "File uploads in lead forms",
        description:
          "Visitors can upload files into a lead form from the widget and from chat, and the files are kept with the lead.",
        category: "new",
      },
      {
        title: "Ila builds it for you",
        description:
          "Ila can set up the lead form, the agent that collects it and the automation that follows, and can list your lead forms and automations.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-10-13",
    title: "Images in chat, and a conversation cloud",
    summary:
      "Paste or drop images into a chat and agents can read them. Conversations show as a cloud you can search.",
    items: [
      {
        title: "Send images to an agent",
        description:
          "Paste, pick or drop images into the dashboard chat, the embedded widget or the API. The agent reads them with a vision model, only when the conversation has an image, and remembers what it saw.",
        category: "new",
      },
      {
        title: "Pick the vision model",
        description:
          "Choose which model reads images in Settings. It is separate from the model your agent talks with.",
        category: "new",
      },
      {
        title: "Conversation cloud",
        description:
          "Your conversations appear as a cloud with search, and a toggle to go back to the classic list. Your choice is remembered.",
        category: "new",
      },
    ],
  },
  {
    date: "2026-10-11",
    title: "Shared accounts and members",
    summary:
      "Bring other people into your account, and decide who can see and use what.",
    items: [
      {
        title: "Invite members",
        description:
          "Admins invite people by email. Each member signs in with their own identity and works in the shared account.",
        category: "new",
      },
      {
        title: "Members portal",
        description:
          "Manage members and invitations in one place. Admins can see what other members have as metadata, never their content.",
        category: "new",
      },
      {
        title: "Private by default, shared on purpose",
        description:
          "What you create stays yours until you share it, with a person or a group, one resource at a time.",
        category: "new",
      },
      {
        title: "Delete artifacts",
        description:
          "Artifacts you no longer need can be deleted, and OpenAI sign-ins refresh themselves instead of expiring.",
        category: "improved",
      },
      {
        title: "A responsive dashboard",
        description:
          "The dashboard and the public site adapt to smaller screens, and your email no longer crowds the navigation bar.",
        category: "improved",
      },
    ],
  },
  {
    date: "2026-10-10",
    title: "Build with Ila, and kits",
    summary:
      "Ila, InnomightLabs' solution builder, sets up what you describe in a chat: agents, knowledge bases, skills, tools and chat widgets. Everything she builds is kept together as a kit you can change, roll back or remove as one.",
    items: [
      {
        title: "Build with Ila",
        description:
          "Tell Ila what you need, or pick one of her ideas, such as a website support agent, a lead qualifier with email alerts, a web research team or a report studio. She shows you a drawing of the plan and builds only when you approve it.",
        category: "new",
      },
      {
        title: "Kits",
        description:
          "Everything one build creates is a kit, listed on the Build with Ila page with what it holds. Each change you approve is a new version, and Ila only ever changes or removes what the kit itself built, never the things you added yourself.",
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
        title: "Ila asks only what you know",
        description:
          "When a skill needs something only you can tell her, such as where lead emails should go, the chat shows a short form for it. Ila writes the rest of the setup herself.",
        category: "new",
      },
      {
        title: "Web search for your agents",
        description:
          "Agents can search and read the web through Tavily. Ila asks you to connect it from a card in the chat, and you sign in once for every agent that uses it.",
        category: "new",
      },
      {
        title: "Changes that finish or put everything back",
        description:
          "If a build fails part-way, or the server restarts in the middle of one, everything it had done is undone, so you're never left with half a solution.",
        category: "improved",
      },
      {
        title: "Ila's conversations stay on her page",
        description:
          "Building with Ila no longer fills your conversations list; her conversations are on the Build with Ila page.",
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
