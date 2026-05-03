# innomightlabs-code-assist

This VS Code extension is the starting point for an Innomightlabs-powered coding assistant. The first implemented feature is a simple `Explain Code` flow:

- Select code in the editor
- Right-click and choose `Explain Code`
- Read the result in the `Innomightlabs` sidebar

## What exists today

- An editor context menu command named `Explain Code`
- A sidebar webview that shows loading, result, and error states
- A backend client layer that is ready for API integration
- A mock fallback response so you can test the extension before wiring the real backend

## Configure the backend

Open VS Code settings and set:

- `innomightlabsCodeAssist.apiBaseUrl`
- `innomightlabsCodeAssist.apiKey`

If either value is missing, the extension returns a mock explanation instead of making a network call.

## Current backend contract

The extension currently uses the widget backend flow:

- `GET /widget/config`
- `GET /widget/conversations`
- `POST /widget/conversations`
- `POST /widget/conversations/{conversationId}/messages`

Authentication is:

- `X-API-Key: <public widget key>`
- Google sign-in for a visitor token, stored by the extension after OAuth completes

If your backend contract changes, update `src/innomightlabsClient.ts` accordingly.

## Run the extension

```bash
yarn compile
```

Then press `F5` in VS Code to launch an Extension Development Host.

## Good next steps

- Replace the mock fallback with your real backend endpoint and payload shape
- Add streaming or incremental updates in the sidebar
- Add a prompt selector such as `Explain`, `Refactor`, or `Find Bugs`
- Move API key storage from plain settings to `context.secrets`
