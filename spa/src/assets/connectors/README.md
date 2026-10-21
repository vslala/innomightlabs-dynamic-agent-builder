# Connector brand marks

These assets identify all configured MCP providers and Google account connectors. They are bundled by
Vite and served from our origin: rendering a connector never requests an icon from a third party.
The brands remain their owners' trademarks; use them only to identify the service.

Refreshed from the providers' sites on 2026-10-20:

| File | Download source |
| --- | --- |
| `notion.png` | https://www.notion.com/front-static/logo-ios.png |
| `linear.svg` | https://linear.app/static/favicon.svg?v=2 |
| `supabase.png` | https://supabase.com/favicon/apple-icon-180x180.png |
| `atlassian.png` | https://www.atlassian.com/apple-touch-icon.png |
| `github.svg` | https://github.githubassets.com/favicons/favicon.svg |
| `sentry.svg` | https://sentry-brand.storage.googleapis.com/sentry-glyph-black.svg |
| `tavily.svg` | https://www.tavily.com/icon.svg |
| `cloudflare.svg` | https://cdn.jsdelivr.net/npm/simple-icons@v16/icons/cloudflare.svg (Simple Icons; vendor site downloads were blocked) |
| `context7.png` | https://context7.com/favicon.ico (PNG image) |
| `canva.png` | https://static.canva.com/domain-assets/canva/static/images/apple-touch-180x180-1.png |
| `deepwiki.png` | https://www.google.com/s2/favicons?domain=deepwiki.com&sz=128 (cached site favicon; direct vendor downloads returned HTTP 429) |
| `microsoft_learn.png` | https://learn.microsoft.com/favicon.ico (converted to PNG) |
| `exa.svg` | https://exa.ai/images/logo/exa-logo-blue.svg (symbol extracted from wordmark, geometry unchanged) |
| `hugging_face.svg` | https://huggingface.co/front/assets/huggingface_logo-noborder.svg |
| `stripe.png` | stripe.com apple-touch-icon |
| `hubspot.png` | hubspot.com favicon |
| `slack.png` | Slack marketing icon (a.slack-edge.com) |
| `mail.png` | https://www.gstatic.com/images/branding/product/2x/gmail_2020q4_96dp.png |
| `hard_drive.png` | https://www.gstatic.com/images/branding/product/2x/drive_2020q4_96dp.png |
| `google_ads.png` | https://www.gstatic.com/images/branding/product/2x/ads_96dp.png |
| `linkedin.svg` | Simple Icons LinkedIn mark (CC0), in LinkedIn blue; used by the Social tab (`api/src/connectors/social/networks/linkedin.py`) |

`ConnectorIcon.tsx` resolves the backend's `icon` key to `<icon>.png|svg`. The legacy Google Ads
account key `megaphone` resolves to `google_ads`. Keep one asset per key to avoid ambiguous selection.

Brand tiles have a white background for contrast in either theme and use `object-fit: contain` so
marks are not cropped. `GLYPH_MARKS` adds padding for transparent GitHub, Atlassian, Gmail, Drive and
Google Ads, Cloudflare, Exa, Microsoft Learn and Hugging Face glyphs. Sentry already has whitespace in its SVG; the other app icons include their own
background or spacing. `connectionIcon.ts` recognizes known MCP hostnames for hand-added connections,
so Installed, Your own server and the details dialog reuse the same marks. Recognition only affects
presentation, not provider membership, authorization or installation state. Unrecognized custom servers
use a server symbol; unknown icon keys retain a lettered tile.

To update a mark, replace the file and update its source above. Prefer SVG or a high-resolution PNG
(Canva is now 180px rather than its 32px favicon). Do not add remote URLs to the renderer.
`ConnectorIcon.test.tsx` checks all icon keys in the backend provider/account definitions, local asset
rendering, image signatures, minimum PNG dimensions, and fallback behavior.
