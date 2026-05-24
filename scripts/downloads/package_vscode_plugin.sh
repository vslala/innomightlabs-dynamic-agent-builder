#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PLUGIN_DIR="${ROOT_DIR}/plugins/ide/vscode/innomightlabs-code-assist"
OUT_DIR="${ROOT_DIR}/dist/downloads/vscode"
ARTIFACT_BASENAME="innomightlabs-code-assist.vsix"

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

hash_sources() {
  (
    cd "$PLUGIN_DIR"
    find package.json yarn.lock tsconfig.json esbuild.js src media README.md CHANGELOG.md LICENSE \
      -type f 2>/dev/null \
      | sort \
      | while read -r file; do
          hash_file "$file"
        done \
      | if command -v sha256sum >/dev/null 2>&1; then sha256sum | awk '{print $1}'; else shasum -a 256 | awk '{print $1}'; fi
  )
}

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

if [ ! -f "$PLUGIN_DIR/package.json" ]; then
  echo "Missing VS Code package.json at $PLUGIN_DIR" >&2
  exit 1
fi

echo "Packaging VS Code plugin..."
(
  cd "$PLUGIN_DIR"
  yarn install --frozen-lockfile || yarn install
  yarn run package
  npx --yes @vscode/vsce package --out "$OUT_DIR/$ARTIFACT_BASENAME"
)

cp "$PLUGIN_DIR/README.md" "$OUT_DIR/README.md"
if [ -f "$PLUGIN_DIR/media/innomightlabs.svg" ]; then
  cp "$PLUGIN_DIR/media/innomightlabs.svg" "$OUT_DIR/icon.svg"
elif [ -f "$PLUGIN_DIR/media/innomightlabs-activitybar.svg" ]; then
  cp "$PLUGIN_DIR/media/innomightlabs-activitybar.svg" "$OUT_DIR/icon.svg"
else
  cat > "$OUT_DIR/icon.svg" <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#111827"/><path d="M18 44V20h7l7 12 7-12h7v24h-7V31l-5 8h-4l-5-8v13z" fill="#fff"/></svg>
SVG
fi

VERSION="$(node -e "console.log(require(process.argv[1]).version)" "$PLUGIN_DIR/package.json")"
SHA256="$(hash_file "$OUT_DIR/$ARTIFACT_BASENAME")"
SOURCE_HASH="$(hash_sources)"

cat > "$OUT_DIR/plugin-build.json" <<JSON
{
  "id": "vscode",
  "name": "Innomight VS Code Plugin",
  "category": "Developer Tools",
  "summary": "Build, test, and manage Innomight agents directly from VS Code.",
  "package_version": "$VERSION",
  "artifact_local_name": "$ARTIFACT_BASENAME",
  "artifact_stem": "innomightlabs-code-assist",
  "artifact_extension": ".vsix",
  "artifact_content_type": "application/octet-stream",
  "readme_local_name": "README.md",
  "icon_local_name": "icon.svg",
  "sha256": "$SHA256",
  "source_hash": "$SOURCE_HASH"
}
JSON

echo "VS Code plugin packaged at $OUT_DIR/$ARTIFACT_BASENAME"
