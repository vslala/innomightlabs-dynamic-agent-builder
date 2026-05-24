# LLD: Multimodal Image Generation V1

## Goal

Add explicit image generation to InnomightLabs agents without changing behavior for agents whose selected model does not support image generation. The feature should attach to the agent's selected model through a capability registry owned by the image feature, persist generated images in S3, save generated images into chat history, and expose enough metadata for the SPA and WordPress AI plugin to show image support only when available.

V1 is image generation only. Image understanding, image editing, proactive agent-driven image generation, quotas, and billing limits are intentionally designed for but not implemented in the first cut.

## Current System Facts

- Agents store provider and model as plain fields: `agent_provider` and `agent_model` in `api/src/agents/models.py`.
- The create/update agent schema currently fetches provider model choices in `api/src/agents/router.py` via `_load_agent_model_choices()`.
- OpenAI models come from `OPENAI_MODELS` settings through `ModelsService.get_openai_models()` in `api/src/llm/models.py`.
- Chat messages are persisted in DynamoDB through `MessageRepository` and currently support text attachments only in `api/src/messages/models.py`.
- Dashboard chat streams over `POST /agents/{agent_id}/{conversation_id}/send-message` and consumes `SSEEvent` from `api/src/llm/events.py`.
- WordPress provider-style generation already uses `POST /widget/generate-text` in `api/src/widget/router.py`.
- Terraform has S3 patterns for artifacts/widget buckets, but no conversation media bucket yet.

## OpenAI/Codex API Notes

This repository does not currently use a normal OpenAI API-key flow for OpenAI chat. `api/src/llm/providers/openai.py` calls an OAuth-backed Codex/ChatGPT responses endpoint from `settings.openai_oauth_responses_url`, which defaults to `https://chatgpt.com/backend-api/codex/responses`.

That means public OpenAI image-generation docs are useful for concepts and expected payload shapes, but they are not sufficient implementation proof for this codebase. A Codex endpoint compatibility spike was run to answer these questions:

- Confirm whether the Codex/ChatGPT responses endpoint accepts the `image_generation` tool for the OAuth credentials this app stores.
- Confirm whether it returns image output as base64, file IDs, URLs, or another internal event shape.
- Confirm whether generated images can be requested explicitly with the selected agent model, or whether a separate image-capable model/tool must be specified.
- Capture the exact streamed/non-streamed event types before implementing the OpenAI adapter.

The internal image provider interface should therefore model Innomight's needs, not the public OpenAI SDK. The probe results below confirm that the Codex endpoint supports image generation over the existing OAuth path, so implement `CodexOpenAIImageGenerationProvider` using the documented stream contract.

Official references:

- https://platform.openai.com/docs/guides/images/image-generation
- https://platform.openai.com/docs/guides/tools-image-generation
- https://platform.openai.com/docs/models/gpt-image-1

Treat these references as public API context only. Do not assume the Codex OAuth endpoint accepts the same paths, auth, or response schema.

## Codex Image Generation Probe Results

Probe date: 2026-05-24.

Local source:

- DynamoDB table: `dynamic-agent-builder-local`
- Provider settings: local `ProviderSettings#OpenAI`, `auth_type=oauth`
- Agent model used for the probe: `gpt-5.4`
- Endpoint: `POST https://chatgpt.com/backend-api/codex/responses`
- Auth: `Authorization: Bearer <OpenAI OAuth access token>`

### Streamed Request

The Codex/ChatGPT responses endpoint accepts the image generation tool with the same OAuth credentials already stored by the app.

```json
{
  "model": "gpt-5.4",
  "instructions": "Generate the requested image.",
  "input": [
    {
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": "Generate a tiny simple test image: a green circle centered on a white background."
        }
      ]
    }
  ],
  "tools": [
    {
      "type": "image_generation"
    }
  ],
  "store": false,
  "stream": true
}
```

Result:

- HTTP status: `200`
- Response body format: server-sent events, same `data: {...}\n\n` framing used by current OpenAI text streaming.
- `Content-Type` header was not set in the observed response.
- Image bytes are returned inline as PNG base64, not as file IDs or URLs.

Observed event sequence:

```text
response.created
response.in_progress
response.output_item.added
response.image_generation_call.in_progress
response.image_generation_call.generating
response.image_generation_call.partial_image
response.output_item.done
response.output_item.added
response.content_part.added
response.output_text.done
response.content_part.done
response.output_item.done
response.completed
```

Image payload events:

```json
{
  "type": "response.image_generation_call.partial_image",
  "background": "opaque",
  "item_id": "ig_...",
  "output_format": "png",
  "output_index": 0,
  "partial_image_b64": "<png base64 len=843728>",
  "partial_image_index": 0,
  "quality": "low",
  "sequence_number": 5,
  "size": "1254x1254"
}
```

```json
{
  "type": "response.output_item.done",
  "item": {
    "id": "ig_...",
    "type": "image_generation_call",
    "status": "generating",
    "action": "generate",
    "background": "opaque",
    "output_format": "png",
    "quality": "low",
    "result": "<png base64 len=843728>",
    "revised_prompt": "A tiny simple test image: a solid green circle centered on a plain white background, minimal and clean.",
    "size": "1254x1254"
  },
  "output_index": 0,
  "sequence_number": 6
}
```

The adapter should use `item.result` from the `response.output_item.done` event where `item.type == "image_generation_call"` as the final image bytes. `partial_image_b64` can be ignored for V1 unless the UI later wants progressive previews.

The final assistant text message can be empty:

```json
{
  "type": "response.output_item.done",
  "item": {
    "id": "msg_...",
    "type": "message",
    "status": "completed",
    "content": [
      {
        "type": "output_text",
        "text": ""
      }
    ],
    "phase": "final_answer",
    "role": "assistant"
  }
}
```

### Non-Streamed Request

The same request with `"stream": false` is rejected:

```json
{
  "detail": "Stream must be set to true"
}
```

Result:

- HTTP status: `400`
- Content-Type: `application/json`

Conclusion: the Codex image generation adapter must stream.

### Tool Configuration Probe

Default tool request:

```json
{
  "type": "image_generation"
}
```

`response.created.response.tools`:

```json
[
  {
    "type": "image_generation",
    "background": "auto",
    "model": "gpt-image-2",
    "moderation": "auto",
    "n": 1,
    "output_compression": 100,
    "output_format": "png",
    "quality": "auto",
    "size": "auto"
  }
]
```

Explicit tool request:

```json
{
  "type": "image_generation",
  "model": "gpt-image-1",
  "size": "1024x1024",
  "quality": "low",
  "output_format": "png"
}
```

`response.created.response.tools`:

```json
[
  {
    "type": "image_generation",
    "background": "auto",
    "model": "gpt-image-2",
    "moderation": "auto",
    "n": 1,
    "output_compression": 100,
    "output_format": "png",
    "quality": "auto",
    "size": "1024x1024"
  }
]
```

Conclusion:

- The selected agent model `gpt-5.4` can request image generation when the `image_generation` tool is present.
- A separate image model does not need to be selected by the user.
- The Codex backend normalizes the image tool model to `gpt-image-2`.
- The `size` option is accepted.
- The explicit `model` option is ignored or normalized by the backend.
- The explicit `quality` option was normalized to `auto` at `response.created`, though the final generated image event can report the backend-selected concrete quality such as `low`.

### Adapter Contract From Probe

The OpenAI/Codex provider adapter should:

1. Always set `"stream": true`.
2. Add `{"type": "image_generation"}` to `tools`.
3. Use the selected agent model as the top-level `model`.
4. Allow supported tool options such as `size`, but do not rely on forcing a specific image model.
5. Parse SSE events until `response.completed`, `response.failed`, or `error`.
6. Collect final image outputs from `response.output_item.done` events where:
   - `item.type == "image_generation_call"`
   - `item.result` is present
   - `item.output_format` is present, defaulting to `png` only if missing
7. Base64-decode `item.result` and upload the bytes to S3.
8. Persist `revised_prompt`, `size`, `quality`, `background`, and `output_format` as image metadata where available.
9. Treat empty assistant text as successful if at least one image was produced.

## Design Principles

1. Agent-owned capability registry, not scattered conditionals.
   The agent image-generation subdomain owns the mapping of provider/model to image-generation support. Agent and LLM models stay mostly generic.

2. Explicit domain boundary.
   Add `api/src/agents/image_generation/` for image capability resolution, provider dispatch, S3 persistence, and image-generation request/response models. This is an agent subdomain because the operation is "ask this agent to generate an image."

3. Persist assets separately from message text.
   DynamoDB stores image metadata and S3 keys. S3 stores the generated bytes.

4. Hide unavailable UI.
   SPA and WordPress metadata should expose image controls only when the selected agent model supports the image feature.

5. Future extension without rewiring.
   The capability model should support later additions such as `image_understanding`, `image_editing`, `image_variation`, quota policies, and proactive tool-driven image generation.

## Capability Model

Add an agent image-generation registry:

`api/src/agents/image_generation/capabilities.py`

```python
from dataclasses import dataclass
from enum import StrEnum


class ImageCapability(StrEnum):
    GENERATION = "image_generation"
    UNDERSTANDING = "image_understanding"
    EDITING = "image_editing"


@dataclass(frozen=True)
class ImageModelCapability:
    provider: str
    model_id: str
    capabilities: frozenset[ImageCapability]
    generation_model: str | None = None
    default_size: str = "1024x1024"
    default_quality: str = "medium"
    output_format: str = "png"


class ImageCapabilityRegistry:
    def __init__(self, entries: list[ImageModelCapability]) -> None:
        self._by_provider_model = {
            (entry.provider.lower(), entry.model_id): entry
            for entry in entries
        }

    def for_agent_model(self, provider: str, model_id: str | None) -> ImageModelCapability | None:
        if not model_id:
            return None
        return self._by_provider_model.get((provider.lower(), model_id))

    def supports(self, provider: str, model_id: str | None, capability: ImageCapability) -> bool:
        entry = self.for_agent_model(provider, model_id)
        return bool(entry and capability in entry.capabilities)
```

Initial OpenAI/Codex entries should come from settings rather than hardcoded code where possible:

- `OPENAI_IMAGE_GENERATION_MODELS`: comma-separated selected agent models that enable the feature.
- `OPENAI_IMAGE_GENERATION_BACKEND`: `codex_oauth` for the current repository integration, or a future explicit backend value if API-key image generation is added.
- Do not require `OPENAI_IMAGE_GENERATION_MODEL` for the Codex OAuth backend. The observed endpoint normalizes the image tool model to `gpt-image-2`.

This keeps the requested ownership model: the image feature knows which selected models unlock image generation. The selected text/chat model does not need to declare its own features.

`ModelInfo` should grow a non-breaking optional field:

```python
capabilities: list[str] = Field(default_factory=list)
```

`ModelsService.get_openai_models()` should populate `capabilities` by asking `ImageCapabilityRegistry`. The SPA can then render model options or agent badges with capability metadata. Existing callers that ignore the new field continue to work.

## API Contract

Add explicit authenticated endpoint:

`POST /agents/{agent_id}/{conversation_id}/generate-image`

Request:

```json
{
  "prompt": "A realistic product photo of ...",
  "size": "1024x1024",
  "quality": "medium",
  "output_format": "png"
}
```

Response:

```json
{
  "agent_id": "agent-id",
  "conversation_id": "conversation-id",
  "user_message_id": "message-id",
  "assistant_message_id": "message-id",
  "images": [
    {
      "image_id": "uuid",
      "url": "https://...",
      "s3_key": "agents/agent-id/conversations/conversation-id/messages/message-id/20260524T031500Z_uuid.png",
      "mime_type": "image/png",
      "width": 1024,
      "height": 1024,
      "size_bytes": 123456,
      "prompt": "A realistic product photo of ..."
    }
  ]
}
```

Use a normal JSON response for V1 rather than SSE because generation is explicit and usually returns one final asset. A later V2 can add SSE progress if providers expose useful intermediate events.

Error behavior:

- `404`: agent or conversation not found.
- `409`: conversation belongs to another agent.
- `422`: invalid prompt/options.
- `403`: selected model does not support image generation.
- `500`: provider/storage error.

For the dashboard UI, direct pasted images are out of scope for generation V1 because image understanding is not implemented. The paste handler should show a dialog if the current agent lacks image input support. When image understanding is added, this should route through the same registry with `ImageCapability.UNDERSTANDING`.

## WordPress Contract

Add provider-style endpoint:

`POST /widget/generate-image`

Request:

```json
{
  "prompt": "Generate a blog hero image about ...",
  "context": {
    "source": "wordpress_ai_client",
    "site_url": "https://example.com",
    "model_config": {}
  },
  "model": "innomight-memory-agent"
}
```

Response:

```json
{
  "images": [
    {
      "url": "https://...",
      "mime_type": "image/png",
      "width": 1024,
      "height": 1024
    }
  ],
  "agent_id": "agent-id",
  "conversation_id": "wordpress-ai-client-agent-sitehash",
  "message_ids": {
    "user_message_id": "message-id",
    "assistant_message_id": "message-id"
  }
}
```

The WordPress plugin should update `InnomightModelMetadataDirectory.php` to advertise image output only when the backend says image generation is available for the API key's agent. If the WordPress AI Client requires static metadata, add a second model ID such as `innomight-memory-agent-image` only when compatible with its provider model contract; otherwise expose capability through provider availability/config discovery.

Add an `InnomightImageGenerationModel` alongside `InnomightTextGenerationModel` if the WordPress AI Client has a dedicated image-generation interface. If the installed AI Client API does not provide that interface, keep the backend endpoint ready and ship the plugin metadata update after confirming the exact interface names.

## Storage Design

User-proposed shape:

`innomightlabs-conversations-meta/{agent_id}/{conversation_id}/{message_id}_{timestamp}.{img_ext}`

Recommended shape:

`s3://innomightlabs-conversations-meta/agents/{agent_id}/conversations/{conversation_id}/messages/{message_id}/{timestamp}_{image_id}.{ext}`

Reasoning:

- Stable prefixes make bulk deletion and operational browsing cleaner.
- The agent folder remains the top-level deletion boundary.
- Multiple images for one assistant message are naturally grouped.
- The filename can stay unique without encoding too many dimensions in one segment.

Example:

`agents/agt_123/conversations/conv_456/messages/msg_789/20260524T031500Z_5d2c.png`

Deletion:

- Conversation delete should delete `agents/{agent_id}/conversations/{conversation_id}/`.
- Agent delete should delete `agents/{agent_id}/`.
- Use paginated `ListObjectsV2` plus batched `DeleteObjects`; do not assume one call is enough.

Visibility:

- Keep the bucket private.
- Store `s3_key` and generate presigned GET URLs for API responses and message history.
- Use a short TTL, e.g. `CONVERSATION_MEDIA_PRESIGN_TTL_SECONDS=900`.

## Message Model Changes

Add generated image metadata to messages:

```python
class MessageImage(BaseModel):
    image_id: str
    s3_key: str
    filename: str
    mime_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    prompt: str | None = None
    created_at: datetime


class MessageImageResponse(BaseModel):
    image_id: str
    url: str
    filename: str
    mime_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    prompt: str | None = None
```

`MessageResponse` should add:

```python
images: list[MessageImageResponse] = Field(default_factory=list)
```

The repository should not know how to sign URLs. Either:

- Add a `MessageResponseFactory` in `api/src/messages/responses.py`, or
- Let routers/services pass an optional image URL signer into `to_response()`.

Prefer `MessageResponseFactory` to keep S3 concerns out of the domain model.

Generated image turn:

1. Save a user message with the prompt text.
2. Call image provider.
3. Upload generated bytes to S3.
4. Save assistant message with content such as `Generated image: {prompt}` and `images=[...]`.
5. Return response with presigned URLs.

## Backend Service Layout

Add:

```text
api/src/agents/image_generation/
├── __init__.py
├── capabilities.py
├── models.py
├── provider.py
├── service.py
└── storage.py
```

Responsibilities:

- `capabilities.py`: registry and support checks.
- `models.py`: request/response/image artifact models.
- `provider.py`: `ImageGenerationProvider` protocol plus provider factory.
- `storage.py`: S3 put, presign, delete-prefix helpers.
- `service.py`: validates agent/conversation ownership and model capability, orchestrates provider/storage/message persistence.

This package should be imported by `api/src/agents/router.py` for dashboard endpoints and by `api/src/widget/router.py` for provider-style WordPress generation. Keep it below `agents` unless another product area needs the same primitives independently.

Provider protocol:

```python
class ImageGenerationProvider(Protocol):
    async def generate(
        self,
        prompt: str,
        credentials: dict[str, Any],
        options: ImageGenerationOptions,
    ) -> list[GeneratedImageBytes]:
        ...
```

OpenAI/Codex adapter:

- Reuse `ensure_valid_openai_credentials()` for OAuth-backed OpenAI credentials.
- Use direct HTTP via `httpx`, matching `api/src/llm/providers/openai.py`.
- Use `settings.openai_oauth_responses_url` or a dedicated `OPENAI_OAUTH_IMAGE_GENERATION_URL` only after the compatibility spike confirms the endpoint.
- Normalize whatever the Codex endpoint returns into `GeneratedImageBytes` before storage. If it returns file IDs or temporary URLs, the adapter must fetch bytes server-side before S3 upload so Innomight remains the system of record for chat history.
- Do not introduce the OpenAI SDK for the OAuth-backed Codex endpoint; it targets the public API-key API and would obscure the integration this repo actually uses.
- If the Codex endpoint cannot generate images, keep this adapter unimplemented and return a clear capability/configuration error rather than silently falling back to a different auth path.

Provider dispatch:

```python
class ImageProviderFactory:
    def get(self, provider_name: str) -> ImageGenerationProvider:
        return self._providers[provider_name.lower()]
```

This keeps unsupported providers explicit and avoids router-level `if provider == ...` checks.

## Terraform Changes

Add `terraform/conversation_media.tf`:

```hcl
resource "aws_s3_bucket" "conversation_media" {
  bucket = var.conversation_media_bucket

  tags = {
    Name        = var.conversation_media_bucket
    Environment = var.environment
  }
}

resource "aws_s3_bucket_public_access_block" "conversation_media" {
  bucket = aws_s3_bucket.conversation_media.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "conversation_media" {
  bucket = aws_s3_bucket.conversation_media.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "conversation_media" {
  bucket = aws_s3_bucket.conversation_media.id

  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_iam_role_policy" "lambda_conversation_media" {
  name = "${var.project_name}-lambda-conversation-media"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:ListBucket"]
        Resource = aws_s3_bucket.conversation_media.arn
        Condition = {
          StringLike = {
            "s3:prefix" = ["agents/*"]
          }
        }
      },
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.conversation_media.arn}/agents/*"
      }
    ]
  })
}
```

Add variables:

```hcl
variable "conversation_media_bucket" {
  description = "Private S3 bucket for generated conversation media"
  type        = string
  default     = "innomightlabs-conversations-meta"
}
```

Add Lambda env vars in `terraform/lambda.tf`:

```hcl
CONVERSATION_MEDIA_BUCKET = aws_s3_bucket.conversation_media.id
CONVERSATION_MEDIA_PRESIGN_TTL_SECONDS = "900"
OPENAI_IMAGE_GENERATION_BACKEND = var.openai_image_generation_backend
OPENAI_IMAGE_GENERATION_MODELS = var.openai_image_generation_models
```

Important: this bucket name is globally unique in AWS. If `innomightlabs-conversations-meta` is already taken in another account or environment, use an environment suffix while preserving the object key structure.

## SPA Changes

Types:

- Add model `capabilities?: string[]` to `AgentApiService` schema types.
- Add `images?: MessageImage[]` to `spa/src/types/message.ts`.

Conversation UI:

- In `ConversationDetail.tsx`, resolve the current agent and whether it has `image_generation`.
- Show an image-generation button/control only when supported.
- Add an explicit image prompt dialog or inline mode. V1 should not overload the normal message send button.
- Render generated assistant image messages as image thumbnails with click-to-open.
- When a pasted file is an image and the agent does not support image input, show a dialog: `This agent's selected model does not support image attachments. Choose a multimodal model to attach images.`

Avoid adding image files to the existing `useFileAttachments()` text attachment path. Create a separate hook later for input images when image understanding lands. This prevents base64 image blobs from being stored in DynamoDB by accident.

## WordPress Plugin Changes

Files likely touched:

- `plugins/wordpress/innomightlabs-ai-connector/src/Metadata/InnomightModelMetadataDirectory.php`
- `plugins/wordpress/innomightlabs-ai-connector/src/Provider/InnomightProvider.php`
- New image model adapter beside `InnomightTextGenerationModel.php`
- Potential REST client helper changes under `includes/class-innomight-ai-client.php`

Implementation notes:

- Add image output modality only for image-capable model metadata.
- Call `/widget/generate-image`.
- Return the image URL or bytes in the shape expected by WordPress AI Client's image-generation contract.
- Keep `/widget/generate-text` unchanged.

## Agent Delete Cleanup

Update `AgentRepository.delete_by_id()` orchestration point carefully. The repository currently deletes only DynamoDB agent rows. Do not inject S3 into the repository directly if avoidable.

Preferred change:

- Add `AgentService.delete_agent(agent_id, user_email)` in `api/src/agents/service.py`.
- Service calls:
  1. `AgentRepository.delete_by_id()`
  2. `ConversationMediaStorage.delete_agent_prefix(agent_id)`
- Router depends on service rather than repository for deletion.

Conversation delete should similarly move media cleanup into a service if more deletion behavior is added:

- `ConversationService.delete_conversation(conversation_id, user_email)`
- Delete `agents/{agent_id}/conversations/{conversation_id}/` after validating ownership.

## Testing Plan

Backend unit tests:

- `api/tests/test_agent_image_capabilities.py`
  - registry returns support for configured OpenAI model.
  - unsupported model returns false.
  - missing model returns false.

- `api/tests/test_agent_image_storage.py`
  - generated S3 key matches `agents/{agent_id}/conversations/{conversation_id}/messages/{message_id}/...`.
  - delete-prefix paginates and batches correctly with mocked S3 client.

- `api/tests/test_agent_image_generation_service.py`
  - unsupported model raises/returns 403.
  - supported model saves user and assistant messages.
  - generated image metadata is persisted and response URLs are presigned.
  - provider failure does not save assistant image message.

- `api/tests/test_agents_router.py`
  - agent response/model choices include capability metadata.
  - delete agent invokes media cleanup.

- `api/tests/test_conversations_router.py`
  - delete conversation invokes media cleanup.

Frontend tests if test harness exists:

- image generation control hidden for unsupported agent.
- control visible for supported agent.
- generated image messages render thumbnails.
- pasted image with unsupported agent opens an explanatory dialog.

Terraform validation:

```bash
cd terraform
terraform fmt
terraform validate
```

Repo test command after implementation:

```bash
cd api
uv run pytest -v
```

## Implementation Sequence

1. Add `api/src/agents/image_generation/` capability registry and settings using the documented Codex OAuth stream contract above.
2. Extend model metadata responses with optional capabilities.
3. Add message image models and response URL factory.
4. Add S3 media storage helper.
5. Add the Codex OAuth image provider adapter.
6. Add image generation service and dashboard endpoint.
7. Add widget `/widget/generate-image`.
8. Add Terraform bucket, env vars, and Lambda IAM.
9. Add deletion cleanup services for agent/conversation media prefixes.
10. Update SPA controls and image rendering.
11. Update WordPress metadata/model adapter.
12. Add tests and run backend suite.

## Open Questions Before Implementation

1. Should generated images be publicly shareable via long-lived URLs, or is short-lived presigned access sufficient for V1?
2. Should V1 support multiple images per prompt, or hard-limit to one image until quotas/billing are designed?
3. Should the WordPress plugin expose generated image bytes, URLs, or both to downstream WordPress AI Client consumers?
4. Should local development use LocalStack/MinIO for S3 tests, or keep storage tests fully mocked?

## Resolved Probe Questions

1. Does the Codex OAuth responses endpoint support explicit image generation for the configured OAuth credentials?
   Yes. `POST /backend-api/codex/responses` accepted `tools: [{"type": "image_generation"}]` with the local OAuth credentials. 

2. Does it return base64, file IDs, URLs, or another internal event shape?
   It returns inline PNG base64 in `response.output_item.done.item.result`. It also streams `partial_image_b64`, which V1 can ignore.

3. Can generated images be requested with the selected agent model, or must a separate image model be selected?
   The selected agent model `gpt-5.4` worked as the top-level model. The user does not need to select a separate image model. The backend normalizes the image tool model to `gpt-image-2`.

4. What are the streamed and non-streamed behaviors?
   Streaming is required. `stream: true` returns SSE events. `stream: false` returns HTTP 400 with `{"detail": "Stream must be set to true"}`.
