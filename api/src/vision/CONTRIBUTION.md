# Vision Contribution Guide

`vision/` lets people attach images to a chat message and lets the agent read them. The agent never sees pixels: it calls the native `read_image` tool, which sends the images to the **account's own vision model** (Settings → Image Reading, separate from the agent's model) and hands the analysis back. Design and decisions: [LLD-image-input-and-read-image-tool](../../../docs/LLD-image-input-and-read-image-tool.md).

## Layout

```text
src/vision/
  models.py        VisionSettings (one item per account), ImageUpload (ledger row), ImageRef, ImageInputLimits
  repository.py    VisionSettingsRepository; ImageUploadRepository (save, find, atomic claim)
  policy.py        image_input_availability(agent): the one rule every surface asks
  images.py        normalise_image: decode, verify, strip EXIF, downscale (Pillow)
  uploads.py       ImageUploadService: store (pending), attach (bind to a message), open_bytes
  limits.py        Upload rate limits for the widget (visitor + key) and /v1 (key)
  http.py          Shared route helpers: read an upload, serve an image, dashboard URL
  context.py       <attached_image> tags for the conversation, recall lines, index_images
  analysis.py      ImageReader: the vision call, concurrency, caching the description
  router.py/schemas.py   /vision/settings (+ form schema)
  errors.py        ImageInputError(code, message, status); rendered by the handler in src/exceptions.py
```

## Rules that keep it correct

- **One availability rule.** Routes, the SPA, the widget shell and the tool all use `image_input_availability` / `require_image_input`. Don't re-derive "is it on" anywhere else. The agent's account decides, not the caller's.
- **Keys.** Settings: `Account#{id}` / `VisionSettings`. Upload ledger: `CONVERSATION#{id}` / `IMAGE#{image_id}`, which no message query reads; `delete_by_conversation` and the guest closer remove it with the conversation. Bytes: `agents/{agent}/conversations/{conversation}/uploads/{image_id}.{ext}` in the conversation media bucket, so the existing prefix deletes cover them.
- **Pending then attached.** An upload is `pending` (DynamoDB `ttl` + S3 tag `retention=pending-upload`, expired by the bucket's lifecycle rule). `ImageUploadRepository.claim` flips it to `attached` atomically: only its uploader, once, before it expires. Always claim through `ImageUploadService.attach`.
- **The uploader is an identity string each surface picks and reuses**: dashboard `user_id`, widget `visitor_id`, `/v1` `conversation.actor_id`. Upload and send must use the same one.
- **Errors are `ImageInputError`** with a stable `code` and a message fit to show. Don't raise bare `HTTPException` for image problems (rate limits are the exception: they need `Retry-After`).
- **The description is the agent's note.** It is saved on `Message.image_attachments[i].analysis`, shown in the conversation as `<attached_image>`, and never returned to clients.
- **A prompt always looks again.** `read_image` returns the saved description only when called with no prompt. The saved description is prompt-independent; never overwrite it.
- **Vision calls are part of the user's message.** They add no subscription message; token usage is recorded as `vision:{model}`.

## How to add a provider's vision support

1. Render `ImageBlock` in the provider's message converter (`src/llm/providers/<name>/chat.py`, or the shared
   `src/llm/wire/` format it speaks) and add it to `tests/test_vision_provider_blocks.py`.
2. In the provider's catalog (`src/llm/providers/<name>/catalog.py`), give its `reads_images` rule (the vendor's
   modality field when it has one, otherwise a documented rule) and tag models with
   `chat_capabilities(reads_images=...)`. Which models read images is the catalog's answer; nothing here lists them.
3. Add cases to `tests/test_catalog_capabilities.py`.

Tests: `uv run pytest tests/test_vision_*.py -q` (uploads, policy, tool, turn, routes for the dashboard, widget and `/v1`, settings).
