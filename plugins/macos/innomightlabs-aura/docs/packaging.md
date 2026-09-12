# Packaging Aura for other people

`./scripts/package.sh` produces `build/Aura.dmg`. It runs the tests, archives Release, signs,
builds the disk image, and notarizes — skipping whichever of those it lacks credentials for and
saying so rather than producing something that looks finished and is not.

```
./scripts/package.sh                                  # build what's possible now
AURA_NOTARY_PROFILE=AuraNotary ./scripts/package.sh    # the full, shareable build
AURA_SKIP_TESTS=1 ./scripts/package.sh                 # iterate on packaging itself
```

## What is needed for a build other people can open

Three things, in order. Only the third is optional-ish, and skipping it still shows a warning.

**1. A Developer ID Application certificate.** This is the gap today — the machine has only an
*Apple Development* certificate, which signs builds for your own registered Macs. A build signed
with it is rejected on anyone else's machine. Verified rather than assumed:

```
$ spctl --assess --type execute -vv /Volumes/Aura/Aura.app
/Volumes/Aura/Aura.app: rejected
origin=Apple Development: ... (3AGTV68923)
```

Create one in Xcode ▸ Settings ▸ Accounts ▸ Manage Certificates ▸ **+** ▸ *Developer ID
Application*, or at developer.apple.com. It needs a paid Apple Developer Program membership
(~$99/year). Team `N88DX83XHU` is already configured in `project.yml`.

**2. The Hardened Runtime**, which notarization requires. Already on for Release, with
`Aura.entitlements` declaring the two device entitlements it would otherwise block:

```
com.apple.security.device.camera
com.apple.security.device.audio-input
```

Screen recording needs no entitlement — it is gated at runtime by TCC, not by the sandbox.
Debug deliberately leaves the Hardened Runtime off so the development loop is unaffected.

**3. Notarization.** One-time credential setup:

```
xcrun notarytool store-credentials AuraNotary \
  --apple-id "you@example.com" \
  --team-id "N88DX83XHU" \
  --password "<app-specific-password>"
```

The password is an *app-specific* password from appleid.apple.com, not your Apple ID password.
After that, `AURA_NOTARY_PROFILE=AuraNotary ./scripts/package.sh` submits the DMG, waits, and
staples the ticket so it validates offline.

## Why signing matters more for Aura than for most apps

macOS binds camera, microphone and screen-recording permissions to an app's **code signature**,
not its path. Two consequences:

- An unsigned or ad-hoc-signed build loses its granted permissions every time it is rebuilt, so
  testers get re-prompted — or silently denied — on each new version.
- Once properly signed with a stable Developer ID, permissions persist across updates.

For a screen recorder this is the difference between a build people can use and one that
appears broken.

## Handing out an unsigned build anyway

Occasionally useful for someone who will take your word for it. On macOS 15 the old
right-click ▸ Open bypass no longer works:

```
xattr -dr com.apple.quarantine /Applications/Aura.app
```

The only UI route is System Settings ▸ Privacy & Security ▸ **Open Anyway**, which appears after
the first blocked launch. Expect to walk people through it, and expect permission prompts to
reappear after every update.

## What is in the disk image

`Aura.app` plus an `/Applications` symlink, so the drag-to-install gesture is obvious. About
7 MB: the WhisperKit transcription model is **not** bundled — it downloads from Hugging Face on
first use and caches outside the app. Worth mentioning to testers, since their first
transcription pauses to fetch it.

## The Mac App Store route, and what it would cost in work

The $99/year membership covers both direct distribution and the App Store, so the money is the
same either way. The work is not. Four things in Aura would have to change, and the first is
the expensive one.

**App Sandbox is mandatory** for the Mac App Store, and Aura is not sandboxed. Concretely:

- `SessionFolder.defaultBaseDirectory` builds its path from
  `FileManager.default.homeDirectoryForCurrentUser`. Under the sandbox that returns the app's
  *container* (`~/Library/Containers/com.innomightlabs.aura/Data`), not the real home — so
  recordings would silently land inside the container instead of `~/Movies/Aura`. Reaching the
  real folder needs `com.apple.security.assets.movies.read-write` **and** obtaining the URL
  through `FileManager.url(for: .moviesDirectory, in: .userDomainMask)` rather than
  string-building from the home directory. Verify the resolved path on a sandboxed build before
  trusting it.
- `com.apple.security.network.client` is required for `api.innomightlabs.com` and for
  WhisperKit's model download.
- The camera and audio-input entitlements are already declared.
- ScreenCaptureKit itself is fine under the sandbox — screen recording is gated by TCC, not by
  the sandbox — so the recorder does not need redesigning.
- The Keychain item in `AgentSettings` moves into the app's own access group. Expected to work,
  worth testing rather than assuming.

**App Review has to be able to exercise the AI panel.** It needs a `pk_live_…` key that a
reviewer does not have. The panel already degrades gracefully when unconfigured
(`AgentSettings.isConfigured` gates it), so the app is reviewable as-is, but supply a test key
in App Store Connect's review notes or the feature will be treated as non-functional.

**WhisperKit downloads a model on first use.** Guideline 2.5.2 forbids downloading executable
code; a CoreML model is data, not code, so this is allowed. Reviewers occasionally ask — say so
in the review notes rather than waiting for the question.

**Nothing live may ship inside the bundle.** The agent key currently lives in the Keychain or an
environment variable, which is correct. Keep it that way.

### Direct distribution is probably the better first step

Same membership fee, and for a tool like this it avoids most of the above: no sandbox work, no
15–30% cut, and updates ship the moment they are built instead of waiting on review. The
trade-offs are that you own update delivery (Sparkle is the usual answer) and you get no App
Store discovery. Aura is one certificate away from it today.

## Version numbers

`MARKETING_VERSION` and `CURRENT_PROJECT_VERSION` in `project.yml`. Bump the marketing version
for anything you hand out; macOS uses the build number to tell two builds of the same version
apart, so bump that too when re-issuing.
