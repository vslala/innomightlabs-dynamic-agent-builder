# Conversation Entry Components Guide

This directory owns the conversation cloud, the classic sidebar list and the first-message composer used by `../Conversations.tsx`. Routes and API orchestration stay in the parent screens; active chat belongs to `../ConversationDetail.tsx` and `src/components/chat/`.

## Layout and flow

`../Conversations.tsx` shows the conversations in one of two views, switched by `ConversationViewToggle.tsx` (Cloud, the default, or Classic). The choice is remembered in `localStorage` (`conversationView.ts`; anything but a saved "classic" means the cloud, and blocked storage is tolerated). The search text and the composer's contents are shared, so switching views loses nothing.

- **Cloud:** a column with a count, the toggle and search, the conversation cloud (it takes all the space left), and the composer docked at the bottom (`docked`, without its heading).
- **Classic:** the original two-column screen: `ConversationSidebar.tsx` (search, new conversation, delete, agent labels; the toggle sits in its header) beside the composer centred under its heading.

The page loads conversations and agents, filters by the search text, creates the conversation and navigates with the first message, and owns delete (both views call back).

`cloud/ConversationCloud.tsx` shows the conversations as titles on a sphere that turns in any direction. Newer titles are bigger and warmer: colour is a heat map from blue (oldest) to red (newest), by rank among the conversations shown, so it always spreads. Hovering a title (mouse) or holding a finger on it (touch) opens `cloud/ConversationCard.tsx` with the agent, dates and description, an Open link and a delete button that asks for confirmation. A click or tap opens the conversation. A card holds the cloud still while it is open, and any press outside the cloud, Escape, or a drag closes it. Keyboard focus on a title turns it to the front and opens its card.

`cloud/useCloudMotion.ts` owns the motion: slow idle drift, a drag that rolls the ball under the pointer, a flick that dies down, long-press and drag detection, and bringing one title to the front. It writes `transform` and `opacity` straight to the titles every frame, so React does not render 60 times a second. `cloud/cloudMath.ts` holds the geometry (points on a sphere, rotation, perspective, heat colours) as plain functions, tested in `cloud/cloudMath.test.ts`.

`ConversationStartComposer.tsx` composes shared `ChatComposer`, `TokenUsageIndicator`, and agent selection with `ConversationStartMode` (`chat` or `image`). Respect feature flags and agent capability constraints when exposing image mode.

## Extension and styling

Add callback/data props rather than importing services into these presentation components. Keep shared attachment/composer behavior in `src/components/chat/`. Conversation filtering and paging belong to the parent/service; use the existing user-visible-conversation handling instead of exposing internal builder conversations accidentally.

Keep the cloud cheap to animate: change only `transform` and `opacity` per frame, and avoid `filter`, `backdrop-filter` and animated shadows on anything that moves. Titles are real links in newest-first order, so keyboard and screen-reader users get a plain list. `prefers-reduced-motion` turns off the idle drift. The cloud sets `touch-action: none` so a drag turns it instead of scrolling the page.

## Verification

From `spa/`: `yarn eslint src/pages/dashboard/conversations src/pages/dashboard/Conversations.tsx`, then `yarn test`, `yarn lint`, `yarn build`. The maths is covered by `cloud/cloudMath.test.ts` and the saved view by `conversationView.test.ts`; there is no DOM test library, so check the gestures with `yarn dev`: drift, drag in every direction, flick, hover card and crossing to it, click to open, search, delete with confirmation, Tab and Escape, a long press and a swipe on a phone-sized screen, the empty and no-match states, and switching between Cloud and Classic (including after a reload).
