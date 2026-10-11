# Downloads Service Guide

`DownloadsApiService.ts` exposes plugin catalog and detail metadata from `/downloads/plugins`, with types in `src/types/downloads`.

- Both calls deliberately use `{ skipAuth: true }`: no dashboard bearer or active-account header should be attached. Keep public download discovery usable while signed out.
- Encode `pluginId` in the detail path. Return the typed catalog/detail response rather than fetching release bytes in this metadata service.
- The class is exported as well as `downloadsApiService`; preserve both entry points. Shared client error/401 interception still runs even with skipAuth.

No adjacent tests currently. Add anonymous-call options, encoded-ID and response-contract tests; use `yarn test src/services/downloads` from `spa/` once added. See [services guide](../CONTRIBUTION.md).
