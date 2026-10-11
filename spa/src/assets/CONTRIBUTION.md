# Bundled Assets Contribution Guide

## Purpose and layout

`src/assets/brand/` currently contains `innomightlabs-logo.png` and `innomightlabs-logo.jpg`. These are source assets for Vite imports, not a media-upload store. Dashboard Sidebar imports the PNG; preserve inspected consumer paths when changing a filename. Public static files and generated build output live outside this directory.

## Usage and extension

Import a bundled asset from TypeScript/TSX and use the resulting URL, rather than hardcoding `/src/assets/...` in production markup. Vite handles the build URL. Put a new asset in a meaningful local category only when the actual feature needs it; check existing files before adding duplicates or converting formats. Do not add credentials, user/private uploads, generated `dist` output, or large unused source files.

Use descriptive filenames and keep file size appropriate to rendered dimensions. Inspect image contents and consumers before claiming PNG and JPG are interchangeable. Avoid moving public URL-addressed resources into this tree without checking deployment and link requirements.

## CSS and accessibility

Sizing, object-fit, responsive behavior, and theme treatment belong to the consuming component's stylesheet (usually a CSS module), not an asset-specific global CSS file. Dashboard Sidebar currently uses token-based surroundings and inline logo dimensions; check both light and dark backgrounds before replacing the artwork. Informative logos need meaningful alt text; decorative repeated artwork should use empty alt where appropriate. Do not bake essential text into an image without an accessible equivalent.

## Verification

No asset tests are colocated here. Use `yarn build` from `spa/` after changing imported paths, and visually check actual consumers at expected resolutions, narrow widths, and both themes. Confirm a production build resolves the URL and that the image remains legible without layout shifts. A successful import/build does not verify artwork, alt text, or contrast. Documentation-only changes do not require image conversion or a runtime suite.
