# Widget embedding guide

Use this guide to put an InnomightLabs chat on your website: as a floating button, directly inside your page, or in several page sections.

These examples use **`embed.js`**, the iframe-based widget. The older **`widget.js` / `InnomightChat.init()`** implementation in `spa/widget/` only supports floating chat. Adding `data-mode="inline"` to that older script will not enable inline chat. For new integrations, use `embed.js`; when migrating, remove the old script and initialization rather than loading both.

## Before you start

1. Open your agent's **Widget API Keys** in the dashboard and create or select a key.
2. Replace `YOUR_PUBLIC_API_KEY` in one of the examples below with that key (`pk_live_…`). Never use a secret API key in browser code.
3. Configure the key's allowed origins for your page, including the scheme and any port, for example `https://www.example.com` or `http://localhost:5500`. Check the actual origin you serve the page from, not a URL path.
4. Pick **one** installation example. Load `embed.js` only once per page.

The script initializes automatically; do not call `InnomightChat.init()` or another initialization function. Inline containers must exist when the loader mounts. The loader waits for `DOMContentLoaded` if the document is still loading.

## Choose a layout

| What you want | Script configuration | Container needed? |
| --- | --- | --- |
| A floating corner button that opens chat | `data-mode="floating"` (the default) | No |
| A chat always present inside the page, with no corner button | `data-mode="inline"` and `data-target="#chat"` | Yes |
| One or more section chats, with no corner button | `data-mode="none"` and elements marked `data-innomight-chat` | Yes, one per section |
| Section chats plus a floating corner button | `data-mode="floating"` and elements marked `data-innomight-chat` | Yes, for the sections |

### 1. Floating chat

Add this once, for example before your page's closing `</body>` tag:

```html
<script
  src="https://cdn.innomightlabs.com/embed.js"
  data-api-key="YOUR_PUBLIC_API_KEY"
  data-mode="floating"
  async
></script>
```

This creates a bottom-right chat button. The chat panel opens when the visitor selects it. `data-mode="floating"` is explicit here for clarity; omitting it has the same effect.

### 2. Inline chat: inside your page, not floating

Place the container exactly where you want the chat to appear:

```html
<div id="chat" style="width: 100%; height: 600px;"></div>

<script
  src="https://cdn.innomightlabs.com/embed.js"
  data-api-key="YOUR_PUBLIC_API_KEY"
  data-mode="inline"
  data-target="#chat"
  async
></script>
```

- `data-target` is a **CSS selector**. `#chat` selects `id="chat"`; use a unique ID for a single chat.
- The iframe fills the container's width and height. Set an explicit container height; the iframe has a **420px minimum height**, so smaller containers can overflow.
- Inline mode does **not** create a floating launcher. `data-position` has no effect in this mode.
- Inline frames are lazy-loaded as they approach the viewport. They stay in the normal page layout.
- Do not also mark this same target with `data-innomight-chat`, or you will mount two chats in it.

### 3. Section chats only: no floating button

Mark each chat container with `data-innomight-chat`. Use **`data-mode="none"`** on the single script to suppress its own floating or inline chat:

```html
<section>
  <h2>Choose a plan</h2>
  <div
    data-innomight-chat
    data-greeting="Need help choosing a plan?"
    data-prompt="Compare the Starter and Team plans for a small business."
    data-prompt-label="Which plan fits my business?"
    data-auto-prompt="false"
    style="width: 100%; height: 560px;"
  ></div>
</section>

<section>
  <h2>Getting started</h2>
  <div
    data-innomight-chat
    data-greeting="Ask me about getting started."
    style="width: 100%; height: 560px;"
  ></div>
</section>

<script
  src="https://cdn.innomightlabs.com/embed.js"
  data-api-key="YOUR_PUBLIC_API_KEY"
  data-mode="none"
  async
></script>
```

The first section offers a clickable question; it does not send the prompt automatically. The second has no preset question. To add a floating button alongside the sections, change just the script's mode to `floating`.

Section elements are scanned once when the loader mounts. There is no public rescan or mount API for sections added later by a client-side router. Ensure containers are present before loading the script; repeated copies of the script are ignored rather than mounting new sections.

### 4. Customize the appearance

This is a complete floating installation with optional appearance settings. Use it **instead of**, not in addition to, the first installation example:

```html
<script
  src="https://cdn.innomightlabs.com/embed.js"
  data-api-key="YOUR_PUBLIC_API_KEY"
  data-mode="floating"
  data-position="bottom-left"
  data-theme="light"
  data-primary-color="#2563eb"
  data-greeting="Hi! How can we help?"
  data-placeholder="Ask a question…"
  data-launcher-label="Open customer support chat"
  async
></script>
```

These appearance settings also work in inline mode; only `data-position` is floating-only. The launcher label is an accessibility label, not visible button text, and is also used as the iframe title. Your page's CSS does not style the chat's internals; use the supported attributes rather than CSS overrides.

## Complete script configuration reference

Set these attributes on the **`embed.js` script tag**. All are optional except `data-api-key`.

| Attribute | Default | Meaning |
| --- | --- | --- |
| `data-api-key` | Required | Public widget key (`pk_live_…`). Shared by the main chat and all section chats. |
| `data-api-url` | `https://api.innomightlabs.com` in the standard production build | API base URL serving `/embed/{public_key}`. Usually leave unset. Custom loader builds can set a different default. This does not change where the loader script is downloaded from. |
| `data-mode` | `floating` | `floating`, `inline`, or `none`. `none` suppresses the script's own chat, not section chats. Unrecognized values fall back to `floating`. |
| `data-target` | None | CSS selector required for `inline` mode. Must match an existing container; the first matching element is used. Ignored for `floating` and `none`. |
| `data-position` | `bottom-right` | Floating button/panel placement: `bottom-right` or `bottom-left`. |
| `data-theme` | `auto` | `auto` follows the visitor's system preference; `light` and `dark` force a theme. |
| `data-primary-color` | Built-in blue accent | Valid CSS color such as `#2563eb`. Applied to the launcher and chat accents; invalid colors are ignored. Prefer a color with good contrast against white text. |
| `data-greeting` | `Hi! I'm {agent name}. How can I help you today?` | Greeting shown by the chat UI. This is not a message sent to the agent. |
| `data-placeholder` | `Write a message…` | Message-input placeholder. |
| `data-prompt` | None | Preset visitor message. With automatic prompting, sent when the chat is first seen and a visitor session is available, if there is no conversation to resume. |
| `data-prompt-label` | Full prompt text | Short visitor-facing wording for the preset question, instead of displaying the full prompt. Does not replace the actual message sent to the agent. |
| `data-auto-prompt` | `true` | `true` sends the preset prompt automatically; `false` offers a one-click suggestion. Has no effect without a prompt. Use the exact strings `"true"` or `"false"`, not a bare boolean attribute. |
| `data-launcher-label` | `Chat with us` | Accessible label for the floating button/dialog and title of the chat iframe. Does not add visible text to the icon button. |

There are no script attributes for guest access, authentication bypass, allowed origins, agent selection, arbitrary iframe height, or runtime configuration updates. The public key selects the agent; container CSS sets inline dimensions. Set attributes before the loader runs; changing them afterward does not reconfigure a mounted chat.

### Section-level overrides and inheritance

On an element marked `data-innomight-chat`, these attributes override the script's shared appearance and prompting behavior:

| Section attribute | When omitted |
| --- | --- |
| `data-theme` | Inherits the script theme. |
| `data-primary-color` | Inherits the script accent. |
| `data-greeting` | Inherits the script greeting, or uses the default greeting. |
| `data-placeholder` | Inherits the script placeholder, or uses the default placeholder. |
| `data-auto-prompt` | Inherits the script setting (ultimately `true`). |
| `data-prompt` | **No preset prompt.** Does not inherit the script's prompt. |
| `data-prompt-label` | Uses the section's full prompt for the question display. Does not inherit the script's prompt label. Also supplies the section iframe title when present. |

Section chats are always inline and use the script's key and API URL. Set dimensions on each section container. `data-api-key`, `data-api-url`, `data-mode`, `data-target`, `data-position`, and `data-launcher-label` are not per-section overrides.

## Preset questions: automatic versus click-to-send

- With `data-auto-prompt="true"` (or no setting), a floating chat becomes seen when opened; an inline chat becomes seen when it scrolls into view. Sending waits for a signed-in or guest session.
- With `data-auto-prompt="false"`, the visitor chooses the suggestion to send the message. Merely seeing the chat does not send it.
- `data-prompt` is the real question/context sent to the agent. `data-prompt-label` is only the shorter wording displayed to the visitor. Neither is a trusted system instruction.
- Prompts scope conversation history. A returning signed-in visitor can resume an existing conversation instead of triggering the prompt again. Different full prompt text gives a different conversation scope; identical prompts are not isolated just because they appear in different containers.
- Put required context directly in the prompt or the agent's knowledge sources. The loader does not automatically send surrounding page text. Do not put secrets in prompts or other HTML attributes; visitors can inspect them, including the full prompt behind a short label.
- HTML-escape dynamic attribute values (`&quot;` for a double quote, `&amp;` for an ampersand). Prefer assigning `element.dataset.prompt` in JavaScript when constructing attributes programmatically.

## Control the floating chat from your own button

`window.InnomightEmbed` is available after the loader executes, not necessarily immediately after an asynchronous script tag. This complete example registers handlers when the script finishes loading:

```html
<button id="open-support" type="button" disabled>Chat with support</button>

<script>
  function connectSupportChat() {
    const widget = window.InnomightEmbed;
    const button = document.getElementById('open-support');
    if (!widget || !button) return;

    button.disabled = false;
    button.addEventListener('click', () => widget.open());

    widget.on('ready', () => {
      console.log('Chat iframe initialized');
    });
  }
</script>

<script
  src="https://cdn.innomightlabs.com/embed.js"
  data-api-key="YOUR_PUBLIC_API_KEY"
  data-mode="floating"
  onload="connectSupportChat()"
  async
></script>
```

If your site's Content Security Policy disallows inline scripts or event handlers, move the handler into your own allowed JavaScript file and register a `load` listener on the script element before adding it to the document.

| Method | Behavior |
| --- | --- |
| `InnomightEmbed.open()` | Opens the main floating panel. |
| `InnomightEmbed.close()` | Closes the main floating panel. |
| `InnomightEmbed.toggle()` | Toggles the main floating panel. |
| `InnomightEmbed.on(event, callback)` | Subscribes to `ready`, `open`, or `close`; returns an unsubscribe function. |

`ready` means the iframe app has initialized, **not** that the visitor has authenticated or that a conversation is ready. A late `ready` subscriber is called immediately if the iframe is already ready. `open` and `close` report floating-panel state changes, not chat messages.

To stop listening:

```javascript
const unsubscribe = window.InnomightEmbed.on('open', () => {
  console.log('Floating chat opened');
});

// Later, when your page no longer needs the listener:
unsubscribe();
```

The API controls only the script's **main chat**, not section chats. In inline mode, `open()`, `close()`, and `toggle()` do nothing; the inline chat is already present. In `none` mode, all global methods are no-ops, including event registration. There is no public `destroy()`, reconfiguration, or section-control method on `InnomightEmbed`. Do not use the old `InnomightChat` API with this loader.

## Authentication and guest configuration

Google sign-in is available in the iframe widget. To also offer email-based guest entry, enable **Allow guest visitors** on the widget API key in the dashboard. It is off by default and cannot be enabled using a script attribute. The classic `widget.js` still requires Google sign-in.

Guest entry checks email format and mail domain and rejects disposable addresses; it does not verify mailbox ownership. Guests cannot use the agent's skills or shared tools. Guest-start and message limits apply. The entry screen displays the inactivity timeout.

A guest chat ends after inactivity or when the visitor selects **End chat**. Background processing archives it, attempts to email a transcript, and clears active chat data and credentials; this can take a few minutes. Transcript delivery is not guaranteed, and empty chats do not produce an email. Private archives default to 90-day retention. A new guest chat starts fresh; guest history cannot be transferred to Google sign-in. See the [Privacy Policy](https://innomightlabs.com/legal/privacy).

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Still seeing a corner button | Use `embed.js`, not `widget.js`. Set `data-mode="inline"` for one inline chat or `data-mode="none"` for section-only chats. Remove old installations or duplicate scripts. |
| Inline chat is missing | Check `data-target` matches an existing element. The console reports unmatched targets. Make the container visible and give it a height. Scroll near it to trigger lazy loading. |
| Two chats appear in one container | Do not use both `data-target` and `data-innomight-chat` for the same element. |
| Frame is blocked | Check the public key and its allowed origins against the actual host scheme/domain/port. Check browser console and your site's CSP allows the CDN script and API iframe origin. |
| Custom button throws `InnomightEmbed is not defined` | Register controls after the loader's `load` event, as shown above. |
| Section added during navigation does not get a chat | The loader scans once; it does not observe dynamically inserted sections or offer a rescan API. Render the section before loading the script. |
| A question sends without a click | Add `data-auto-prompt="false"` on the script or relevant section. |
| Script prompt does not appear in a section | Section prompts are intentionally not inherited. Set `data-prompt` on the section itself. |
| Custom CSS does not change chat colors | The chat lives in an iframe. Configure the supported theme/accent attributes instead. |
| Guest entry is absent | Enable guest visitors on the API key; there is no `data-allow-guests` option. |

## Implementation references

- [Loader and supported attributes](../embed/loader/index.ts)
- [Loader configuration tests](../embed/loader/index.test.ts)
- [Loader/iframe configuration contract](../embed/shared/protocol.ts)
- [Conversation and prompt behavior](../embed/app/useChat.ts)
- [Public Quick Start](../src/pages/docs/QuickStart.tsx) — published at `/docs/quick-start#embedded-widget`.
- [Embed development guide](../embed/AGENTS.md)

This is a usage guide for existing behavior, not a new widget design. No runtime or deployment changes are required by these examples.
