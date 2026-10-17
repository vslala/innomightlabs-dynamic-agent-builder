#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# mlx-swift (the speech model's runtime) ships a build plugin that command-line builds refuse to
# run until it is trusted; Xcode asks once interactively.
xcodegen generate
xcodebuild -project InnomightLabsAura.xcodeproj -scheme Aura -configuration Debug build -skipPackagePluginValidation
