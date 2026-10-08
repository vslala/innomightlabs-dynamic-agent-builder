#!/usr/bin/env bash
# Builds Aura, installs it to /Applications and launches that copy, so every run is the latest
# build at one fixed path. One path matters beyond convenience: macOS ties the microphone,
# camera and screen recording grants to where the app lives, and a copy launched from
# DerivedData can be a different app to it than the one in /Applications.
set -euo pipefail
cd "$(dirname "$0")/.."

BUNDLE_ID="com.innomightlabs.aura"
INSTALLED_APP="/Applications/Aura.app"

xcodegen generate
xcodebuild -project InnomightLabsAura.xcodeproj -scheme Aura -configuration Debug build
BUILT_PRODUCTS_DIR=$(xcodebuild -project InnomightLabsAura.xcodeproj -scheme Aura -configuration Debug -showBuildSettings 2>/dev/null | awk -F'= ' '/ BUILT_PRODUCTS_DIR /{print $2; exit}')

# A running Aura would otherwise just be brought to the front by `open`, so the new build
# would never start. Quit it the normal way, which lets an in-progress recording finalize.
if pgrep -x Aura >/dev/null; then
    echo "Quitting the running Aura..."
    osascript -e "quit app id \"$BUNDLE_ID\""
    for _ in $(seq 1 30); do
        pgrep -x Aura >/dev/null || break
        sleep 0.5
    done
    if pgrep -x Aura >/dev/null; then
        echo "Aura is still running (a recording may be saving). Quit it and run this again." >&2
        exit 1
    fi
fi

# Replace rather than copy over: `ditto` into an existing bundle would leave behind files the
# new build no longer has.
rm -rf "$INSTALLED_APP"
ditto "$BUILT_PRODUCTS_DIR/Aura.app" "$INSTALLED_APP"
echo "Installed $(defaults read "$INSTALLED_APP/Contents/Info" CFBundleShortVersionString) to $INSTALLED_APP"

open "$INSTALLED_APP"
