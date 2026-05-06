# Innomightlabs Code Assist

`innomightlabs-code-assist` is a VS Code extension that connects your editor to the Innomightlabs widget backend. It lets you sign in with your Innomightlabs Google account, reuse backend conversations, ask targeted questions about selected code, rewrite code in place, and review prior conversation history from the sidebar.

## Setup

Before using the extension, configure the global backend settings in VS Code:

- `innomightlabsCodeAssist.apiBaseUrl`
- `innomightlabsCodeAssist.apiKey`

For the Innomightlabs widget backend, the base URL is typically:

- `https://api.innomightlabs.com`

The API key should be your Innomightlabs widget public key from `innomightlabs.com`.

You can configure these values through:

- VS Code Settings UI
- workspace settings
- the `Configure Backend` command if you expose that flow in your local build

If the backend URL or API key is missing, the extension cannot call the live Innomightlabs backend.

## Sign In Flow

After configuring the backend:

1. Open the `Innomightlabs` activity bar view in VS Code.
2. Click `Sign In with Google`.
3. Complete the Google sign-in flow in your browser through Innomightlabs.
4. The extension stores the returned visitor session locally and uses it for widget conversations.

## Main Features

### Ask About Selected Code

This is the explain flow, but it now takes a user question instead of sending a fixed explanation prompt.

Usage:

1. Select code in the editor.
2. Right-click and choose `Explain Code`.
3. Enter what you want to know about the selected code.
4. The answer appears in the `Code Explanation` sidebar view.

The request includes:

- the selected code
- file path
- language
- your question
- additional tool protocol instructions for runtime context expansion

### Rewrite Selected Code

This flow rewrites only the selected range.

Usage:

1. Select code in the editor.
2. Trigger `Rewrite Selected Code`.
3. Enter the rewrite instruction.
4. The selected code is replaced in place with the returned output.

Shortcut:

- `Alt+K`, then `R`

This flow sends:

- the selected code
- exact selection line and column range
- file path and language
- full document context with selection markers
- your rewrite instruction

### Slash Command Generation

This flow listens for slash-prefixed prompt lines in the editor.

Usage:

1. Type a line beginning with `/`
2. Press Enter
3. The extension treats that line as a generation request and replaces it with generated code

The slash command flow uses the current document, the slash command line, and local indentation context.

### Conversation Sidebar

The main sidebar view lets you:

- sign in and sign out
- create a new conversation
- select an existing conversation
- view the latest answer
- inspect the last selected code block

### Conversation Log

The `Conversation Log` view shows the currently selected conversation as a scrollable history of prior user and assistant messages.

This is useful for:

- checking past prompts
- reviewing previous generated answers
- understanding what context has already been sent in the active thread


## Tool-Capable Runtime

The extension now includes an agent runtime layer that can support tool-assisted context gathering.

At the moment, the runtime can expose tools such as:

- active editor context
- reading a workspace file
- listing workspace files
- searching workspace text

The runtime includes:

- a tool schema registry
- prompt-visible tool contracts
- runtime input validation before tool execution

This is the foundation for future back-and-forth context acquisition where the model can ask for additional IDE or project information before returning a final answer.

## Development

Install dependencies and compile:

```bash
yarn compile
```

For iterative development:

```bash
yarn watch
```

Then press `F5` in VS Code to open an Extension Development Host.

## Packaging

To build a VSIX package:

```bash
npx @vscode/vsce package
```

Then install it in VS Code using:

- `Extensions: Install from VSIX...`

