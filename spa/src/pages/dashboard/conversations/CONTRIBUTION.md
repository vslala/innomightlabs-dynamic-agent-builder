# Conversation Entry Components Guide

This directory owns the sidebar and first-message composer used by `../Conversations.tsx`. Routes and API orchestration stay in the parent screens; active chat belongs to `../ConversationDetail.tsx` and `src/components/chat/`.

## Layout and flow

`ConversationSidebar.tsx` renders conversation links, search, new/delete actions, agent labels/icons, and loading affordances. It accepts typed conversation/agent data and callbacks rather than owning network requests.

`ConversationStartComposer.tsx` composes shared `ChatComposer`, `TokenUsageIndicator`, and agent selection with `ConversationStartMode` (`chat` or `image`). Parent Conversations loads agents/default-agent preference, creates the conversation, and navigates with the initial input. Respect feature flags and agent capability constraints when exposing image mode.

## Extension and styling

Add callback/data props for new entry interactions rather than importing services into these presentation components. Keep shared attachment/composer behavior in `src/components/chat/`, not a second local implementation. Conversation filtering and paging belong to the parent/service; use the existing user-visible-conversation handling instead of exposing internal builder conversations accidentally.

`ConversationSidebar.module.css` and `ConversationStartComposer.module.css` own their respective layouts. Parent `Conversations.module.css` owns the two-column screen; `Conversation.module.css` owns active conversation detail. Keep selectors scoped to the right surface and preserve keyboard-accessible links, button labels, and narrow-width behavior.

## Verification

There are no colocated component tests here. Related builder/chat helpers have tests under `src/services/builder/` and `src/components/chat/`. From `spa/`: `yarn eslint src/pages/dashboard/conversations src/pages/dashboard/Conversations.tsx`, then `yarn test`, `yarn lint`, `yarn build`. Check search/delete/new, default-agent selection, empty agents, first-message navigation, image-mode gating, and sidebar overflow with `yarn dev`.
