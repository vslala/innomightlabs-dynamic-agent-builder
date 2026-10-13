# Vision Settings Service Guide

`VisionSettingsService.ts` reads and saves the account's image reading (`/vision/settings`, schema at `/vision/settings/schema`). Any member may read it; only account admins may save, and the API enforces that.

- The provider and vision-model choices come from the backend's form schema; the API refuses a model that can't read images (`vision_model_unsupported`). Don't filter models in the browser.
- Chat-side image calls live elsewhere: uploads in `services/conversations` (`uploadImage`), availability in `services/agents` (`getImageInput`), the `image_ids` of a send in `services/chat`.
- Design: [LLD-image-input-and-read-image-tool](../../../../docs/LLD-image-input-and-read-image-tool.md).
