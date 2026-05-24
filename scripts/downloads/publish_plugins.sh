#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_ROOT="${ROOT_DIR}/dist/downloads"
BUCKET="${ARTIFACTS_BUCKET:-innomightlabs-artifacts}"
PREFIX="${PLUGINS_PREFIX:-artifacts/plugins}"
EXISTING_MANIFEST="${BUILD_ROOT}/existing-manifest.json"
MANIFEST="${BUILD_ROOT}/manifest.json"

if [ -n "${AWS_PROFILE:-}" ]; then
  echo "Using AWS profile: ${AWS_PROFILE}"
fi

for plugin_id in vscode wordpress; do
  if [ ! -f "${BUILD_ROOT}/${plugin_id}/plugin-build.json" ]; then
    echo "Missing build output for ${plugin_id}. Run package_${plugin_id}_plugin.sh first." >&2
    exit 1
  fi
done

mkdir -p "$BUILD_ROOT"
echo "Fetching existing manifest from s3://${BUCKET}/${PREFIX}/manifest.json if present..."
if ! aws s3 cp "s3://${BUCKET}/${PREFIX}/manifest.json" "$EXISTING_MANIFEST" >/dev/null 2>&1; then
  echo '{"schema_version":1,"plugins":[]}' > "$EXISTING_MANIFEST"
fi

python3 "${ROOT_DIR}/scripts/downloads/generate_plugins_manifest.py" \
  --build-root "$BUILD_ROOT" \
  --existing-manifest "$EXISTING_MANIFEST" \
  --output "$MANIFEST" \
  --prefix "$PREFIX"

python3 - "$MANIFEST" "$BUILD_ROOT" "$BUCKET" <<'PY'
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
build_root = Path(sys.argv[2])
bucket = sys.argv[3]

for plugin in manifest["plugins"]:
    plugin_id = plugin["id"]
    build = json.loads((build_root / plugin_id / "plugin-build.json").read_text(encoding="utf-8"))
    local_artifact = build_root / plugin_id / build["artifact_local_name"]
    local_readme = build_root / plugin_id / build["readme_local_name"]
    local_icon = build_root / plugin_id / build["icon_local_name"]
    artifact = plugin["artifact"]

    uploads = [
        (local_artifact, artifact["key"], artifact["content_type"]),
        (local_readme, plugin["readme_key"], "text/markdown; charset=utf-8"),
        (local_icon, plugin["icon_key"], "image/svg+xml"),
    ]
    for local_path, key, content_type in uploads:
        if not local_path.exists():
            raise SystemExit(f"Missing upload input: {local_path}")
        cmd = [
            "aws",
            "s3",
            "cp",
            str(local_path),
            f"s3://{bucket}/{key}",
            "--content-type",
            content_type,
        ]
        print("+ " + " ".join(cmd))
        subprocess.run(cmd, check=True)
PY

echo "Uploading manifest..."
aws s3 cp "$MANIFEST" "s3://${BUCKET}/${PREFIX}/manifest.json" \
  --content-type "application/json; charset=utf-8"

echo "Published plugin artifacts to s3://${BUCKET}/${PREFIX}/"
