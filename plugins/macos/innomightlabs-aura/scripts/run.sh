#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
xcodegen generate
xcodebuild -project InnomightLabsAura.xcodeproj -scheme Aura -configuration Debug build
BUILT_PRODUCTS_DIR=$(xcodebuild -project InnomightLabsAura.xcodeproj -scheme Aura -configuration Debug -showBuildSettings 2>/dev/null | awk -F'= ' '/ BUILT_PRODUCTS_DIR /{print $2; exit}')
open "$BUILT_PRODUCTS_DIR/Aura.app"
