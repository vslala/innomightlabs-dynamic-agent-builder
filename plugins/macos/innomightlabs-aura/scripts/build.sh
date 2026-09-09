#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
xcodegen generate
xcodebuild -project InnomightLabsAura.xcodeproj -scheme Aura -configuration Debug build
