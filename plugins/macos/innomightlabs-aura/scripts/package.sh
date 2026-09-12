#!/usr/bin/env bash
#
# Builds a distributable Aura.dmg.
#
# Signs and notarizes when a "Developer ID Application" certificate is available, and falls
# back to a development-signed build when it is not — announcing loudly which one happened,
# because the difference decides whether anyone else can actually open the app.
#
#   ./scripts/package.sh
#
# Optional environment:
#   AURA_SIGN_IDENTITY   Signing identity. Default: the first Developer ID Application found.
#   AURA_NOTARY_PROFILE  notarytool keychain profile. Notarization is skipped without it.
#   AURA_SKIP_TESTS      Set to 1 to skip the test run.
#
# One-time setup for a shareable build:
#   1. Create a Developer ID Application certificate
#      (Xcode ▸ Settings ▸ Accounts ▸ Manage Certificates ▸ + , or developer.apple.com).
#      This requires a paid Apple Developer Program membership.
#   2. Store notarization credentials once:
#      xcrun notarytool store-credentials AuraNotary \
#        --apple-id "you@example.com" --team-id "N88DX83XHU" --password "<app-specific-password>"
#      (App-specific passwords come from appleid.apple.com, not your Apple ID password.)
#   3. AURA_NOTARY_PROFILE=AuraNotary ./scripts/package.sh

set -euo pipefail
cd "$(dirname "$0")/.."

BUILD_DIR="build"
ARCHIVE="$BUILD_DIR/Aura.xcarchive"
STAGING="$BUILD_DIR/dmg"
DMG="$BUILD_DIR/Aura.dmg"

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[33m!!  %s\033[0m\n' "$1"; }
fail() { printf '\033[31m!!  %s\033[0m\n' "$1" >&2; exit 1; }

step "Generating the project"
xcodegen generate

step "Preparing the build directory"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

if [ "${AURA_SKIP_TESTS:-0}" != "1" ]; then
  step "Running tests"
  # A build nobody can open is bad; a build that ships a known-broken editor is worse.
  ./scripts/test.sh > "$BUILD_DIR/test.log" 2>&1 || {
    tail -40 "$BUILD_DIR/test.log"
    fail "Tests failed — see $BUILD_DIR/test.log"
  }
  grep -E "Executed .* tests" "$BUILD_DIR/test.log" | tail -1
fi

step "Archiving (Release)"
xcodebuild \
  -project InnomightLabsAura.xcodeproj \
  -scheme Aura \
  -configuration Release \
  -archivePath "$ARCHIVE" \
  archive \
  > "$BUILD_DIR/archive.log" 2>&1 || { tail -40 "$BUILD_DIR/archive.log"; fail "Archive failed"; }

APP_IN_ARCHIVE="$ARCHIVE/Products/Applications/Aura.app"
[ -d "$APP_IN_ARCHIVE" ] || fail "No Aura.app in the archive"

# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

IDENTITY="${AURA_SIGN_IDENTITY:-}"
if [ -z "$IDENTITY" ]; then
  # Only a Developer ID Application certificate produces something another Mac will open.
  IDENTITY=$(security find-identity -v -p codesigning 2>/dev/null \
    | grep "Developer ID Application" \
    | head -1 \
    | sed -E 's/.*"(.*)".*/\1/') || true
fi

DISTRIBUTABLE=0
rm -rf "$STAGING"
mkdir -p "$STAGING"
cp -R "$APP_IN_ARCHIVE" "$STAGING/Aura.app"
APP="$STAGING/Aura.app"

if [ -n "$IDENTITY" ]; then
  step "Signing with: $IDENTITY"
  # --deep is deliberately avoided: it is documented as unreliable for nested code and does
  # not sign frameworks with their own entitlements correctly. Sign inside-out instead.
  find "$APP/Contents/Frameworks" -maxdepth 1 -type d \( -name "*.framework" -o -name "*.dylib" \) 2>/dev/null \
    | while read -r nested; do
        codesign --force --options runtime --timestamp --sign "$IDENTITY" "$nested"
      done

  codesign --force --options runtime --timestamp \
    --entitlements Aura.entitlements \
    --sign "$IDENTITY" \
    "$APP"

  codesign --verify --deep --strict --verbose=2 "$APP" 2>&1 | tail -3
  DISTRIBUTABLE=1
else
  warn "No 'Developer ID Application' certificate found."
  warn "The app stays development-signed, which Gatekeeper will block on other Macs."
  warn "See the header of this script for the one-time setup."
fi

# ---------------------------------------------------------------------------
# Disk image
# ---------------------------------------------------------------------------

step "Building the disk image"
# The Applications symlink is what makes the drag-to-install gesture obvious.
ln -s /Applications "$STAGING/Applications"
hdiutil create \
  -volname "Aura" \
  -srcfolder "$STAGING" \
  -ov -format UDZO \
  "$DMG" > "$BUILD_DIR/dmg.log" 2>&1 || { tail -20 "$BUILD_DIR/dmg.log"; fail "DMG creation failed"; }

if [ -n "$IDENTITY" ]; then
  codesign --force --sign "$IDENTITY" "$DMG"
fi

# ---------------------------------------------------------------------------
# Notarization
# ---------------------------------------------------------------------------

PROFILE="${AURA_NOTARY_PROFILE:-}"
if [ -n "$IDENTITY" ] && [ -n "$PROFILE" ]; then
  step "Notarizing (this waits on Apple, usually a few minutes)"
  xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait \
    || fail "Notarization failed. 'xcrun notarytool log <id> --keychain-profile $PROFILE' explains why."

  step "Stapling the ticket"
  xcrun stapler staple "$DMG"
  xcrun stapler validate "$DMG"

  step "Verifying as Gatekeeper will see it"
  spctl --assess --type open --context context:primary-signature -vv "$DMG" 2>&1 | tail -3
elif [ -n "$IDENTITY" ]; then
  warn "Signed but NOT notarized (AURA_NOTARY_PROFILE is unset)."
  warn "macOS will still warn on first open. Notarize to remove that."
  DISTRIBUTABLE=0
fi

# ---------------------------------------------------------------------------

step "Done"
echo "  $DMG  ($(du -h "$DMG" | cut -f1))"
if [ "$DISTRIBUTABLE" = "1" ]; then
  echo "  Signed and notarized — this opens cleanly on any Mac."
else
  cat <<'NOTE'

  NOT ready to hand out. Recipients will hit Gatekeeper, and because macOS binds
  camera/microphone/screen-recording permissions to an app's signature, an unsigned
  build also loses its granted permissions every time it is rebuilt.

  To open it anyway on a Mac that trusts nothing:
    xattr -dr com.apple.quarantine /Applications/Aura.app

  On macOS 15 the right-click ▸ Open bypass no longer works; the only UI route is
  System Settings ▸ Privacy & Security ▸ "Open Anyway" after the first blocked launch.
NOTE
fi
