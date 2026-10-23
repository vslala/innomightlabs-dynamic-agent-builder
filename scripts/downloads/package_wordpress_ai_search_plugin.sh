#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PLUGIN_DIR="${ROOT_DIR}/plugins/wordpress/innomight-ai-search"
OUT_DIR="${ROOT_DIR}/dist/downloads/wordpress-ai-search"
ARTIFACT_BASENAME="innomight-ai-search.zip"
STAGING_DIR="${OUT_DIR}/staging"

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
    find . -type f \
      ! -path './.git/*' \
      ! -path './node_modules/*' \
      ! -path './vendor/*' \
      ! -path './docs/*' \
      ! -path './tests/*' \
      \( ! -path './.wordpress-org/*' -o -path './.wordpress-org/icon.svg' \) \
      ! -name '.DS_Store' \
      | sort \
      | while read -r file; do
          hash_file "$file"
        done \
      | if command -v sha256sum >/dev/null 2>&1; then sha256sum | awk '{print $1}'; else shasum -a 256 | awk '{print $1}'; fi
  )
}

extract_version() {
  awk -F': ' '/^[[:space:]]*\*?[[:space:]]*Version:/ {print $2; exit}' "$PLUGIN_DIR/innomight-ai-search.php" | tr -d '[:space:]'
}

convert_readme() {
  python3 - "$PLUGIN_DIR/readme.txt" "$OUT_DIR/README.md" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
text = src.read_text(encoding="utf-8")

lines: list[str] = []
for raw in text.splitlines():
    line = raw.rstrip()
    m = re.fullmatch(r"===\s*(.*?)\s*===", line)
    if m:
        lines.append(f"# {m.group(1)}")
        continue
    m = re.fullmatch(r"==\s*(.*?)\s*==", line)
    if m:
        lines.append(f"## {m.group(1)}")
        continue
    m = re.fullmatch(r"=\s*(.*?)\s*=", line)
    if m:
        lines.append(f"### {m.group(1)}")
        continue
    lines.append(line)

dst.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
PY
}

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR" "$STAGING_DIR"

if [ ! -f "$PLUGIN_DIR/innomight-ai-search.php" ]; then
  echo "Missing WordPress plugin entrypoint at $PLUGIN_DIR" >&2
  exit 1
fi

echo "Packaging WordPress AI Search plugin..."
mkdir -p "$STAGING_DIR/innomight-ai-search"
rsync -a "$PLUGIN_DIR/" "$STAGING_DIR/innomight-ai-search/" \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude 'vendor' \
  --exclude 'docs' \
  --exclude 'tests' \
  --exclude '.wordpress-org' \
  --exclude '.DS_Store'

(
  cd "$STAGING_DIR"
  zip -qr "$OUT_DIR/$ARTIFACT_BASENAME" innomight-ai-search
)

convert_readme
if [ ! -f "$PLUGIN_DIR/.wordpress-org/icon.svg" ]; then
  echo "Missing icon at $PLUGIN_DIR/.wordpress-org/icon.svg" >&2
  exit 1
fi
cp "$PLUGIN_DIR/.wordpress-org/icon.svg" "$OUT_DIR/icon.svg"

rm -rf "$STAGING_DIR"

VERSION="$(extract_version)"
SHA256="$(hash_file "$OUT_DIR/$ARTIFACT_BASENAME")"
SOURCE_HASH="$(hash_sources)"

cat > "$OUT_DIR/plugin-build.json" <<JSON
{
  "id": "wordpress-ai-search",
  "name": "Innomight AI Search",
  "category": "WordPress",
  "summary": "Add an AI follow-up chat to your WordPress search results, answered live by your Innomight agent.",
  "package_version": "$VERSION",
  "artifact_local_name": "$ARTIFACT_BASENAME",
  "artifact_stem": "innomight-ai-search",
  "artifact_extension": ".zip",
  "artifact_content_type": "application/zip",
  "readme_local_name": "README.md",
  "icon_local_name": "icon.svg",
  "sha256": "$SHA256",
  "source_hash": "$SOURCE_HASH"
}
JSON

echo "WordPress AI Search plugin packaged at $OUT_DIR/$ARTIFACT_BASENAME"
