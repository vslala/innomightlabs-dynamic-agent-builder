# Artifacts Service Guide

`ArtifactApiService.ts` returns artifact metadata and view/download URL responses from `/artifacts`. Artifact kinds are `html_report`, `image` and `file`.

- List returns an `ArtifactListResponse`, not a bare array. Detail IDs are encoded in paths.
- `/view` and `/download` return `ArtifactUrlResponse`; they do not fetch bytes. Let the consumer handle opening/downloading the returned URL, preserving any expiry metadata rather than treating it as a permanent asset path.
- Keep source metadata distinct from the artifact's identity. Requests use the active dashboard account through `httpClient`; a returned URL is not a reason to bypass metadata authorization.

No adjacent tests currently. Add encoded-ID, list-envelope and view/download-path tests; from `spa/`, use `yarn test src/services/artifacts` after adding them. See [services guide](../CONTRIBUTION.md) for shared validation.
