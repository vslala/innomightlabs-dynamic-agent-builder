# Skills Service Guide

`SkillApiService.ts` separates `/skills` catalog/install schemas from an agent's installed skills under `/agents/{id}/skills`. Types live in `src/types/skills`.

- Install schema returns `FormSchema`. Install sends the typed payload with encoded `skill_id` in the query; update PATCHes the encoded installed-skill path.
- Uninstall has an optional `disconnectOAuth` choice reflected in its query. Keep removing an agent installation distinct from disconnecting shared credentials; don't silently opt into disconnection.
- `startSkillOAuth(path, payload)` uses a supplied route; A2A remote OAuth has the explicit `/skills/agent2agent_client/oauth/start` route. Return authorization-flow responses to consumers rather than opening popups here.
- API owns installation validation and runtime trust decisions, including A2A allowed origins. All current catalog/install requests use dashboard auth/account context.

No adjacent tests currently. Add encoded IDs, uninstall-option and OAuth payload tests; from `spa/`, run `yarn test src/services/skills` once added. See [services guide](../CONTRIBUTION.md).
