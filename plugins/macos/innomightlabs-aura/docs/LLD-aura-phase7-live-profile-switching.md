# Aura Phase 7 — Live Profile Switching

## Context

Phase 6 made *what* gets recorded a user choice, but it is a choice made once, before the
recording starts. A talking-head intro, a screen demo, and a talking-head outro are therefore
three recordings, and joining them is manual editing work that the shot itself already told us
how to do.

This phase makes the profile changeable **while recording**, so one session can be:

```
camera + mic  ──────────────────────────────────────────────────────►   (A)
              ┌─ screen + system audio ─┐   ┌─ screen + system audio ─┐
              └─────────────────────────┘   └─────────────────────────┘ (B)
```

The camera and microphone run unbroken for the whole session; screen and system audio switch on
and off as many times as the user likes. The review window opens on **one** continuous
multi-track timeline, with the camera filling the frame where there is no screen and sitting in
its corner where there is.

### What is already true (and therefore not in this phase)

The composition layer needs **no new concept**. This is the finding that shapes the whole
design, and it is worth being precise about why.

- `LayerInstructionCompositionBuilder.insertClips` clips every source range against
  `available = CMTimeRange(start: .zero, duration: probe.duration)` shifted by that track's
  `timeOffset` (`LayerInstructionCompositionBuilder.swift:161-200`). A file that covers only
  part of the session already places correctly and leaves the rest empty.
- `InsertedVideoLayer.covered` is already `[CMTimeRange]` — a **list**, and its doc comment
  already says why: "a list rather than a single span because the pieces can be disjoint … a
  union would paper over the holes, which is exactly what this bookkeeping exists to prevent"
  (`:86-93`).
- `boundaries(timeline:layers:)` already cuts an instruction at the start and end of every
  covered range, precisely so "the stretch after a source file ended early renders as clean
  background instead of holding a stale final frame" (`:286-293`).
- `instruction(timeRange:…)` already drops a layer instruction for a range the layer does not
  cover, "so an early-ending track — or a hole between two inserted pieces — does not leave an
  instruction pointing at nothing" (`:325-329`).
- `OverlayKeyframe` already carries a time-varying `rect` **and** `visible`, step-interpolated,
  explicitly so "the camera [can] be hidden for one stretch of the recording and visible for
  another" (`SessionEdit.swift:156-166`).
- `CoreImagePiPCompositor` already tolerates a base layer with no frame at a given time —
  `if let base = request.sourceFrame(byTrackID:)` (`CoreImagePiPCompositor.swift:92`) — so the
  styled path degrades to background rather than holding a stale frame.
- `TrackWriter` already anchors on a **shared** `sessionStartTime` rather than "now"
  (`TrackWriter.swift:60`), and `finish` is already a self-contained per-writer operation
  already driven independently per writer (`RecordingController.swift:237-248`).
- `SourceTrackProbe.alignmentCorrection` already exists to place a track whose content starts
  later than the session (`SourceTrackProbe.swift:95-98`).

So "camera full-frame here, corner there" is **ordinary overlay keyframes**, and "this track was
only running during these windows" is **ordinary per-file offset and duration**. Neither the
compositor nor the resolver has to learn that profile switching exists.

The hard-wired parts are elsewhere, and there are exactly three:

| Where | What it assumes |
| --- | --- |
| `RecordingController` (`:21`, `:53`, `:70`) | `sources` is built once by `CaptureSourceFactory.sources(for:)` and never changes until `stop()`. |
| `SessionFolder` (`:64-67`) + `SourceTrackProbe.probeAll` (`:155-173`) + `EventTimeline.trackStartOffsets` (`:24-31`) | One file per `TrackKind`, one `track_start` offset per kind (last-write-wins). |
| `ReviewViewModel.loadFilmstrips` / `loadWaveforms` (`:337-374`) | One media file per lane. |

### Scope

**In:** live add/remove of capture sources against a running session; one file per on-window
("segments") with per-segment alignment; segment-aware probing, resolving and lane rendering;
camera auto-promotion to full frame where no screen covers; a menu-bar preset switcher and a
global hotkey; a `profile_changed` event.

**Out, deliberately:** switching while paused (§5.4); changing the *screen target* mid-session
(the filter is fixed at start — switching display mid-take is a different feature with its own
geometry problem, since render size is fixed for a composition); changing camera or microphone
*device* mid-session; per-segment transcription of a segmented microphone (§7.3).

---

## 1. The design decision

The obvious implementation is `if newProfile.tracks.contains(.screen) && !old.contains(.screen)
{ startScreen() }` per source, per concern — which is the exact shape Phase 6 removed. The
established seam is already the right one: sources are a **list**, and the factory is the single
place that asks "is this source enabled".

So a live profile change is **set reconciliation over that list**, computed in one pure place:

| Concern | Conditional design | Reconciliation design |
| --- | --- | --- |
| What starts | `if` per kind, per direction | `plan.added` |
| What stops | `if` per kind, per direction | `plan.removed` |
| What is left alone | implicit, and easy to get wrong | `plan.retained` |
| `SCStream` owning two kinds | a special case at every site | falls out of keying by kind-set |
| Selection | — | the existing factory, reused verbatim |

The unit of change is the **`CaptureSource`, identified by the set of kinds it owns** — not the
individual `TrackKind`. That is what makes `SCStream` stop being a special case: it produces
screen and system audio from one stream, so "system audio switched off" changes that source's
identity and the source is rebuilt, while "camera unchanged" leaves the camera strictly alone.

### The invariant that shapes the order of operations

**A failed switch must be a no-op.** Turning the screen on for the first time can hit the Screen
Recording TCC prompt, and `SCStream.startCapture()` can reject a configuration. Neither may kill
a recording that is already 40 seconds in. So added sources are prepared *and started* before
anything is retired, and a throw at either step cancels only what was being added.

---

## 2. Segments: one file per on-window

A source that stops and restarts cannot write into one file. Not appending for 30 seconds does
not produce a 30-second hole — for video the last frame's duration extends and renders as a
frozen stale frame, and for audio AVFoundation's handling of a presentation-time jump is
undocumented and would silently desync everything after it. So each on-window gets its own file,
and the files are the truth about when the source was running.

### 2.1 Filenames

`SessionFolder` gains pure naming, and **the first window keeps the unsegmented name**:

```swift
/// The file one on-window of a track is written to.
///
/// Window 0 keeps the unsegmented name (`screen.mov`), so a session that never switched is
/// byte-identical to one recorded before segmenting existed — which keeps every pre-existing
/// session, every derived cache path, and every existing test valid.
static func fileName(for kind: TrackKind, segment: Int) -> String

func url(for kind: TrackKind, segment: Int) -> URL
```

`screen.mov`, `screen-1.mov`, `screen-2.mov`; `system-audio.m4a`, `system-audio-1.m4a`. The
existing `screenURL`/`cameraURL`/`microphoneURL`/`systemAudioURL` become
`url(for: kind, segment: 0)` and stay, because the derived cache helpers
(`filmstripURL(for:)`, `peaksURL(for:)`) are already per-file and generalize for free.

Discovery on reopen is a directory listing filtered by prefix and sorted by parsed index —
never a sequence of existence probes, which a single missing index would silently truncate.
`SessionFolder.existingSessions` already establishes the listing idiom (`:92-99`).

### 2.2 Why later segments place themselves

`TrackWriter.start()` calls `startSession(atSourceTime: sessionStartTime)` with the **original**
session start (`TrackWriter.swift:60`). A writer created 300 s in therefore gets a 300 s leading
empty edit for video — which is exactly the mechanism `SourceTrackProbe.leadingEmptyEdit` already
reads. So:

| | leading empty edit | `recordedStartOffset` | `alignmentCorrection` |
| --- | --- | --- | --- |
| video segment at 300 s | 300 s (written by AVAssetWriter) | 300 s (logged) | ≈ 0 — the file self-places |
| audio segment at 300 s | 0 (AVAssetWriter discards it) | 300 s (logged) | 300 s |

Both rows are already handled by `alignmentCorrection`. This is why the composition layer needs
no change: a segment is just a probe with an offset, and it already knows how to place one.

The one requirement this imposes: **every segment must log its own `track_start` offset**, or an
audio segment plays from zero — early by the entire time it was not recording.

### 2.3 `CaptureContext` owns segment numbering

Sources must not count their own windows. The context already exists to carry "the shared clock
facts every source needs"; it gains the file question too, so numbering has one owner:

```swift
struct CaptureContext: Sendable {
    let folder: SessionFolder
    let sessionStartTime: CMTime

    /// Paused time already elapsed before this source existed.
    ///
    /// Zero for sources created at `start`, non-zero for one added mid-session after a pause.
    /// A fresh `PauseClock` starts at zero, so without this seed a newly added writer would
    /// not rebase by the pauses the long-running writers already rebased by — and its track
    /// would land late by the whole accumulated paused duration.
    let elapsedPausedDuration: CMTime

    /// Which on-window this is, per kind.
    private let segmentIndices: [TrackKind: Int]

    /// A source asks for its own output file rather than naming one, so §2.1's numbering is
    /// not duplicated across four conformers.
    func outputURL(for kind: TrackKind) -> URL {
        folder.url(for: kind, segment: segmentIndices[kind] ?? 0)
    }
}
```

The three sources change one line each: `context.folder.screenURL` →
`context.outputURL(for: .screen)` (`ScreenCaptureSource.swift:45,48`,
`CameraCaptureSource.swift:104`, `MicrophoneCaptureSource.swift:61`).

`TrackWriter.init` gains `elapsedPausedDuration:` and passes it to
`PauseClock(accumulatedPausedDuration:)`. `PauseClock` gains that one initializer parameter,
defaulted to `.zero`.

---

## 3. Reconciliation

New file, `Sources/Aura/Recording/LiveSourcePlan.swift`. Pure, and the only place that decides
what a live profile change does to a running source list.

```swift
/// What a live profile change does to a running source list.
///
/// Sources are matched by the set of kinds they own, which is their identity: one `SCStream`
/// produces screen and system audio together, so switching system audio off changes that
/// source's identity and it is rebuilt rather than reconfigured. A source whose identity is
/// unchanged is *retained untouched* — the camera and microphone files must not be interrupted
/// by a change that has nothing to do with them.
struct LiveSourcePlan {
    let retained: [any CaptureSource]
    let removed: [any CaptureSource]
    let added: [any CaptureSource]

    var isEmpty: Bool { removed.isEmpty && added.isEmpty }
    /// The source list once the plan has been applied, in `TrackKind.allCases` order.
    var resulting: [any CaptureSource] { retained + added }
}

extension CaptureSource {
    /// This source's reconciliation identity.
    var kindKey: Set<TrackKind> { Set(kinds) }
}

extension CaptureSourceFactory {
    static func plan(live: [any CaptureSource], for request: RecordingRequest) -> LiveSourcePlan {
        let desired = sources(for: request)          // reused verbatim — one selection site
        let liveKeys = Set(live.map(\.kindKey))
        let desiredKeys = Set(desired.map(\.kindKey))

        return LiveSourcePlan(
            retained: live.filter { desiredKeys.contains($0.kindKey) },
            removed: live.filter { !desiredKeys.contains($0.kindKey) },
            added: desired.filter { !liveKeys.contains($0.kindKey) }
        )
    }
}
```

No branch per source, and adding a fifth recordable device later changes nothing here.

---

## 4. `RecordingController`

### 4.1 Retirement, unified with `stop()`

Today `stop()` stops every source, logs every offset, then finishes every writer
(`RecordingController.swift:121-152`). Mid-session retirement is the same three steps over a
subset — so it becomes **one** path, which is what stops the two from ever disagreeing:

```swift
/// Stops capturing, records where each track actually began, and finalizes the files.
///
/// Two phases rather than one loop: every device must stop at as nearly the same instant as
/// possible (a sequential stop-then-await-finish would let the last source record however long
/// the first one's file took to finalize), and only then is it safe to finalize.
///
/// The offsets are logged **here** rather than once at session end. A source retired
/// mid-session is no longer in `sources` by the time `stop()` runs, and a segment with no
/// `track_start` is placed at zero — which for audio means playing early by the entire time it
/// was not recording.
private func retire(_ retiring: [any CaptureSource]) async -> [String] {
    for source in retiring { await source.stop() }

    let writers = retiring.flatMap { source in source.writers.map { ($0.key, $0.value) } }
    logTrackStartOffsets(of: writers)
    await finish(writers.map(\.1))
    return writers.compactMap { $0.1.failureReason }
}
```

`stop()` becomes `let failures = await retire(sources)` followed by the existing teardown.
`logTrackStartOffsets` (`:263-274`) loses its dependence on the live `sources` list and takes
the writers it should log, and each event now carries the segment's filename in `path` (§6.1).

### 4.2 The switch

```swift
/// Replaces the live profile without interrupting the sources it has in common.
///
/// Added sources are prepared *and started* before anything is retired, so a refused Screen
/// Recording prompt or a rejected `SCStream` configuration leaves the recording exactly as it
/// was. That is the whole reason this is not `removed`-then-`added`.
func switchProfile(to profile: RecordingProfile) async {
    guard state == .recording, let live = activeRequest else { return }

    let request = live.replacing(profile: profile)
    guard request.isValid else {
        lastError = profile.isRecordable ? .writerSetupFailed("Choose a display to record.")
                                         : .noSourcesSelected
        return
    }

    let plan = CaptureSourceFactory.plan(live: sources, for: request)
    guard !plan.isEmpty else { return }

    let context = makeContext(adding: plan.added.flatMap(\.kinds))
    do {
        for source in plan.added { try await source.prepare() }
        for source in plan.added {
            source.onFailure = sourceFailureHandler
            try await source.start(context: context)
        }
    } catch {
        plan.added.forEach { $0.cancel() }     // discards the partial files
        lastError = (error as? RecordingError) ?? .writerSetupFailed(error.localizedDescription)
        return                                  // no-op: `sources` was never touched
    }

    _ = await retire(plan.removed)
    sources = plan.resulting
    segmentCounts.advance(plan.added.flatMap(\.kinds))
    activeRequest = request
    currentProfile = profile
    logEvent(.profileChanged, at: CMClockGetTime(CMClockGetHostTimeClock()),
             label: profile.eventLabel)
}
```

Three pieces of new controller state, all of them things the controller already half-held:

- `activeRequest: RecordingRequest?` — so a switch needs only a profile. The screen target is
  fixed at start, and `MenuBarContentView.currentRequest` already always supplies one even when
  the starting profile does not use it (`MenuBarContentView.swift:104-111`), so switching *into*
  screen mid-session already has its filter. `RecordingRequest` gains
  `replacing(profile:) -> RecordingRequest`.
- `segmentCounts: [TrackKind: Int]` — the next window index per kind.
- `sourceFailureHandler` — the closure already built inline at `:73-77`, extracted so §4.2 and
  `start` wire it identically.

`RecordingStateMachine` needs **no new state or trigger**. Switching happens strictly within
`.recording` and changes the source list, not the session lifecycle — `applyTransition` was
never gating source composition.

### 4.3 Camera resolution: delete `CameraQuality`

`CameraQuality(profile:)` picks 720p when the starting profile has a screen track and 1080p when
it does not (`CameraCaptureSource.swift:20-23`). Live switching makes the *starting* profile a
bad predictor: start in B and switch to A and the camera is 720p upscaled to fill the frame, and
the preset cannot be changed later without reconfiguring the `AVCaptureSession` and interrupting
the camera file.

With switching, any camera track can become the full frame, so there is no case left where 720p
is knowably sufficient. `CameraQuality` is **deleted** and the camera always records at
`.hd1920x1080` — one type and one branch removed, at the cost of a larger `camera.mov` on
PiP-only sessions. Stated plainly because it is a real trade-off, not a free win.

---

## 5. Session log

### 5.1 `track_start` is keyed by file

```swift
/// How far behind the session start each recorded file's first sample was, keyed by file name.
///
/// Keyed by **file** rather than by track kind: a source switched on and off repeatedly writes
/// one file per on-window and each has its own offset, so a kind-keyed dictionary silently kept
/// only the last one. `track_start` events written before segmenting carried `label` (the kind)
/// and no `path`; those key to the kind's window-0 filename, which is the single file such a
/// session wrote.
var segmentStartOffsets: [String: TimeInterval]
```

This replaces `EventTimeline.trackStartOffsets` (`:24-31`), whose last-write-wins behaviour is
the one existing outright bug this phase must fix. `RecordingEvent` needs no new field — `path`
already exists and is already used this way by `screen_snapshot`.

### 5.2 One new event kind

```swift
case profileChanged = "profile_changed"
```

Diagnostic only — `EventTimeline` has a `default: break` so older readers are unaffected, and
nothing about playback derives from it. The composition layer learns the windows from the files,
per the principle `RecordingManifest` already states: "Behaviour is never derived from this …
the editor decides what it can do from the files that actually exist" (`:5-11`).

For the same reason `RecordingManifest.profile` stays as written — it is the profile the session
*started* with, and its doc comment is updated to say so rather than the manifest being rewritten
on every switch.

---

## 6. Review layer

### 6.1 A track is now a list of segments

```swift
/// One recorded file, plus where its content belongs on the session timeline.
struct PlacedSegment: Sendable, Equatable {
    let probe: SourceTrackProbe
    /// `probe.alignmentCorrection`, plus the lane's manual slip for audio.
    let timeOffset: CMTime
}
```

`ResolvedVideoLayer` and `ResolvedAudioLane` hold `segments: [PlacedSegment]` in place of
`probe` + `timeOffset`. Geometry and colour tags come from the first segment — every segment of
one kind is the same device at the same preset, which is exactly why changing the screen target
mid-session is out of scope.

`SourceTrackProbe.probeAll` (`:155-173`) returns segments per kind, reading offsets from
`segmentStartOffsets` by filename.

`TimelineResolver.resolve` (`:21-29`) changes only in that `byKind` maps to `[SourceTrackProbe]`;
`byKind[.screen] ?? byKind[.camera]` and the base/overlay roles are unchanged. Base stays
**screen** when a screen track exists at all, because render size is fixed for a composition and
the screen is the layer whose legibility depends on it.

`insertClips` (`:161-200`) gains one outer loop over segments, appending into the same `covered`
list it already builds. That is the entire composition-layer diff.

### 6.2 One real arithmetic fix

`ReviewViewModel:287` takes `recordedDuration = probes.map(\.duration).max()`. A late **audio**
segment has a small duration and a large offset (§2.2), so a max over durations understates the
recording. It becomes a max over `timeOffset + duration` across every segment.

### 6.3 Camera promotion — the only genuinely new review code

New file, `Sources/Aura/Review/Composition/CameraOverlaySeed.swift`. Pure; session-time seconds
in, keyframes out.

```swift
/// Seeds the camera overlay from the stretches the screen actually covers.
///
/// Where no screen segment covers the timeline the camera is the only picture, so it fills the
/// frame; where one does, it returns to its corner. Expressed as ordinary `OverlayKeyframe`s —
/// which is why nothing in the compositor needed to learn that profile switching exists, and
/// why the user can still drag, retime or delete any of them afterwards.
enum CameraOverlaySeed {
    static let fullFrame = NormalizedRect(x: 0, y: 0, width: 1, height: 1)

    /// `screenWindows` are the screen segments' spans in session time, ascending and disjoint.
    /// Empty means no screen track, in which case the camera is already the base layer and a
    /// corner rect would be wrong — so a single full-frame keyframe is returned.
    static func keyframes(
        screenWindows: [TimeSpan],
        recordingDuration: TimeInterval,
        corner: NormalizedRect = .defaultCameraOverlay
    ) -> [OverlayKeyframe]
}
```

For windows `[42, 70)` and `[95, 130)` over a 160 s recording:

```
t=0    fullFrame     t=42   corner     t=70   fullFrame
t=95   corner        t=130  fullFrame
```

Wired into the **fallback** document only — `EditDocumentStore.load` (`:39`) already uses
`SessionEdit.initial` solely when there is nothing on disk, so a session the user has already
edited is never re-seeded. `SessionEdit.initial`'s `cameraRect`/`cameraVisible` parameters
(`:322-334`) generalize to `cameraOverlay: [OverlayKeyframe]`.

Known visual characteristic, stated rather than discovered later: a full-frame rect whose aspect
differs from the camera's fails `ResolvedTimeline.canUseLayerInstructions` (`:144-155`) and routes
to `CoreImagePiPCompositor`, which aspect-**fits** (`CoreImagePiPCompositor.swift:93`). So the
camera is letterboxed into the screen's aspect during promoted stretches, not cropped. That is
the correct choice for a webcam and it is what the cheap path would do too — but it is also a
per-frame Core Image pass for those stretches.

### 6.4 Lane rendering

`ReviewViewModel.loadFilmstrips`/`loadWaveforms` (`:337-374`) iterate segments instead of a
single URL per lane, keyed as `[VideoLane: [PlacedFilmstrip]]` and `[AudioLane: [PlacedPeaks]]`,
each carrying the segment's session-time window. Cache URLs already derive per file
(`SessionFolder:30-32`, `:76-78`), so caching needs no change.

`FilmstripLaneView` resolves a slot's frame index from absolute source seconds
(`FilmstripLaneView.swift:65-69`); it becomes "find the segment whose window contains this
moment, then index within it", and draws nothing for a moment no segment covers — which is the
truth about that stretch. The waveform lane changes the same way. `TimelineLane` is unchanged:
the lane set is still one row per kind, and a lane with holes is still one lane.

---

## 7. UI

### 7.1 Menu bar switcher

`MenuBarContentView.recordingContent` (`:121-141`) already renders live controls during
`.recording`/`.paused` and already reads `controller.currentProfile`. It gains a preset `Picker`
bound to `controller.currentProfile`, calling `switchProfile(to:)`, disabled while `.paused`
(§5.4 below). `RecordingPreset.matching(_:)` (`RecordingProfile.swift:86-88`) already maps a
profile back to a preset name, or "Custom".

### 7.2 Global hotkey

The point of this feature is not breaking the take, and a mouse trip to the menu bar breaks the
take. The app has no global-shortcut infrastructure today.

`RegisterEventHotKey` (Carbon) is the right mechanism: it works under the Hardened Runtime, needs
no entitlement, and — unlike `NSEvent.addGlobalMonitorForEvents` — needs no Accessibility grant,
which matters for an app already asking for camera, microphone and screen recording.

New file, `Sources/Aura/App/GlobalHotkey.swift`, with the bindings as a list rather than a
`switch`, matching the shape of the rest of this phase:

```swift
/// One system-wide shortcut and what it does.
struct HotkeyBinding {
    let keyCode: UInt32
    let modifiers: UInt32
    let action: @MainActor () -> Void
}

/// Registers a list of bindings and routes the one Carbon event handler back to them by id.
/// A list, so adding a shortcut is one element and never a branch in a dispatch function.
@MainActor final class GlobalHotkeyRegistry { … }
```

Default bindings: ⌥⌘1…⌥⌘5 for `RecordingPreset.allCases`. Registered while recording and
unregistered on stop, so Aura holds no global shortcuts when it is not recording.

### 7.3 What the user is not told, and should be

Two honest surfaces, both cheap:

- Switching screen on restarts the `SCStream`, which takes ~100–300 ms, and the macOS screen
  recording indicator reappears. The *recorded* offset is measured from the first real sample
  (`TrackWriter.firstAppendedHostTime`), not from the keypress, so the timeline is correct by
  construction — but the first fraction of a second after the hotkey is not screen-recorded.
- A microphone that is itself switched off and on becomes multi-segment, and
  `SessionTranscriber.transcribe(microphoneURL:)` (`:22`) takes a single file. Out of scope:
  for now the transcript is produced from the microphone's **first** segment and the Voice lane
  reports the rest as untranscribed, rather than silently transcribing part of a session and
  presenting it as whole.

---

## 8. Implementation order

Each step leaves the app working and testable.

1. **Segment plumbing, no behaviour change.** `SessionFolder.fileName(for:segment:)`,
   `CaptureContext.outputURL(for:)`, `TrackWriter`/`PauseClock` pause seeding. Every source
   still records window 0, so the output is byte-identical. Existing tests must stay green.
2. **Segment-aware reading, still no switching.** `segmentStartOffsets` keyed by file,
   `probeAll` returning segments, `PlacedSegment`, `TimelineResolver`, `insertClips`, the §6.2
   duration fix. Verified by hand-constructing a two-segment session folder — this is where the
   composition claims of §"What is already true" get proven rather than assumed.
3. **`LiveSourcePlan` + `retire` unification.** Pure and fully unit-testable before anything
   calls it; `stop()` routed through `retire` and re-verified.
4. **`switchProfile`, driven from the menu bar only.** First on-device test: A→B→A, then
   A→B→A→B→A. Confirm on hardware that a second `SCStream` starts without re-prompting, and
   that the camera and microphone files are genuinely uninterrupted.
5. **`CameraOverlaySeed`** and its wiring into the fallback document.
6. **Lane rendering** (§6.4), then the **global hotkey** (§7.2).

Steps 1–3 are behaviour-preserving and where the risk actually is; 4–6 are the feature.

---

## 9. Testing

Pure units, in the style of the existing suite (`Tests/AuraTests/`):

- `LiveSourcePlanTests` — A→B and B→A produce the expected added/removed/retained; camera and
  microphone are retained across both; `{screen, systemAudio}` → `{screen}` rebuilds the stream
  source rather than retaining it; an unchanged profile plans empty.
- `SessionFolderTests` (extend) — window 0 keeps the legacy filename for all four kinds;
  indices round-trip; segment discovery sorts by index and survives a non-contiguous set.
- `EventTimelineTests` (extend) — two `track_start` events for one kind both survive; a legacy
  event with `label` and no `path` keys to the window-0 filename.
- `CameraOverlaySeedTests` — no windows → one full-frame keyframe; one interior window → four
  keyframes; a window touching t=0 emits no redundant leading keyframe; a window reaching the
  end emits no trailing one; two windows → the §6.3 table.
- `TimelineResolverTests` (extend) — a two-segment screen track resolves one base layer with two
  segments; render size still comes from the screen.
- `PauseClockTests` (extend) — a clock seeded with elapsed paused duration rebases identically
  to one that accumulated it live. This is the desync guard.
- `TrackAlignmentTests` (extend) — an audio segment with a recorded offset and no leading empty
  edit corrects by its full offset; a video segment corrects by ≈ zero.

Needs device verification, not unit tests: a second and third `SCStream` in one process; that
retiring the stream source does not disturb the camera's `AVCaptureSession`; that a switch
during the first second of a recording does not race writer creation.

---

## 10. Alternatives rejected

**One file per kind, with the off-windows recorded as events and intersected at composition
time.** Materially cheaper — `SessionFolder`, `probeAll`, the filmstrip and waveform lanes and
the transcriber would all be untouched, and `insertClips` would gain a window intersection
instead of a segment loop. Rejected because keeping a writer open across an off-window relies on
AVFoundation's undocumented handling of a presentation-time jump in an audio input. If it packs
samples contiguously instead of preserving the gap, every track after the first off-window
desyncs — silently, and only on some durations. The segmented model is correct by construction
instead of correct by hoping.

**Camera as the base layer, screen as an overlay toggled by `visible` keyframes.** Tempting: the
base would then cover the whole session, and repeated toggling would need no segments at all.
Rejected because render size is fixed for a composition and derives from the base — a screen demo
would be rendered at camera resolution, which is the one quality regression this feature cannot
afford.

**A time-varying base layer in `ResolvedTimeline`.** Would express promotion "properly" rather
than via overlay keyframes. Rejected as a speculative abstraction: it changes a type whose doc
comment exists to concentrate uncatchable-exception invariants (`ResolvedTimeline.swift:111-119`),
and it buys nothing over keyframes the user can already see, drag and undo.

---

## 11. Deferred

- **Switching while paused.** Needs a `PauseClock` that can be constructed already-paused, which
  is the one place the clock seeding is easy to get subtly wrong. The switcher is disabled while
  paused instead; the §2.3 seed still handles a *completed* pause before a switch, which is the
  common case.
- **Per-segment transcription** of a segmented microphone (§7.3).
- **Changing screen target, camera device or microphone device** mid-session.
- **Auto-cut on switch** — a `splitPoint` at each profile change would make the boundaries
  addressable in the editor. Cheap to add once `profile_changed` exists, but it is an editing
  opinion and belongs behind a preference rather than in the first version.
