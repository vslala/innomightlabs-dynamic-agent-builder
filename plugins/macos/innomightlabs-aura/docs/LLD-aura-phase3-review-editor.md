# LLD: Aura Phase 3 — Review & Edit Window

Jira: KAN-28 (epic KAN-27). Phase 1 was the recording core
([LLD-aura-phase1-recording-core.md](LLD-aura-phase1-recording-core.md)); Phase 2 (voice control of
the recorder) is still in progress on a branch and is orthogonal to this. Nothing here depends on it
beyond the WhisperKit dependency noted below.

## Scope

After Stop, open a review window over the just-finished session:

- One composited preview — `screen.mov` as the base layer, `camera.mov` as a picture-in-picture
  overlay the user can drag, resize, and hide, with the layout **keyframed over time**.
- Two **separate** waveform lanes (microphone, system audio) with independent gain/mute — kept
  separate rather than pre-mixed so the later edit UI and the agent can address each source.
- A transcript panel, produced on-device, that tracks the playhead.
- Export of the composition to a single file.
- A non-destructive, versioned edit document.

## Architecture

```
SessionEdit  (Codable, Sendable, zero AVFoundation types)  -- edit.json
     |
     |  TimelineResolver.resolve(document:probes:)          -- pure, valid by construction
     v
ResolvedTimeline  (Sendable value type: clips, layer keyframes, audio keyframes,
                   renderSize, frameDuration, base-layer identity, PiPStyle)
     |
     +-- LayerInstructionCompositionBuilder   <- today
     +-- CustomCompositorCompositionBuilder   <- later (rounded corners, borders, blur)
                    |
                    +--> AVPlayerItem   (preview, its own reduced renderSize)
                    +--> ExportEngine   (file)
```

`SessionEdit` is the single source of truth and `EditOperation` is the only way to mutate it. UI
gestures produce operations today; the InnomightLabs agent and voice commands will produce the same
operations later, applied through the same `EditDocumentStore.apply`. That symmetry — not the
playback UI — is the point of this phase.

Playback and export consume the *same* `AVVideoComposition` and `AVAudioMix` objects, so what the
user previews is what gets written.

### Why a pure resolver stage rather than building AVFoundation objects directly

Two reasons, both structural:

- This API surface raises **uncatchable ObjC NSExceptions**, not Swift errors. A non-numeric
  `CMTime`, an overlapping transform ramp, a zero `renderSize`/`frameDuration`, or a layer
  instruction naming an unpopulated track terminates the process. Making `ResolvedTimeline` valid by
  construction — times numeric, keyframes sorted and deduplicated, ramps non-overlapping — moves all
  of that into unit-testable pure code and leaves the builder a mechanical transcription.
- `AVMutableVideoComposition`, `AVMutableVideoCompositionInstruction`, and
  `AVMutableVideoCompositionLayerInstruction` are Swift-deprecated as of macOS 26.0. Their
  `Configuration` replacements are macOS 26+, so with `deploymentTarget: 15.0` we cannot adopt them.
  Confining all mutable-class use to one builder file gives one place to suppress and one place to
  migrate.

Compositions are gated through `isValidForTracks(_:assetDuration:timeRange:validationDelegate:)`
(macOS 15+) in DEBUG before reaching an `AVPlayerItem`.

## Timeline semantics

All four Phase 1 tracks share one `sessionStartTime` and call `startSession(atSourceTime:)`
immediately, so `media_time = host_time - sessionStartTime - accumulatedPausedDuration` is identical
across them. Three consequences drive this design:

**Same origin, different durations.** Capture warm-up differs per source, `TrackWriter.append` drops
samples per-track under backpressure, stop is staggered, and AAC tails round differently. Measured on
a real 54-second session the four files came out 54.23 / 54.12 / 53.86 / 54.02 seconds long — that is
the normal case, not an edge case. So each
asset is inserted as `CMTimeRange(start: .zero, duration: <that asset's duration>)` at composition
time `.zero`, and the timeline length comes from `composition.duration`. `startSession` already
encodes each track's warm-up offset as a **leading empty edit** — using `track.timeRange` as the
source range instead would double-count it. A missing, empty, or truncated track is skipped rather
than fatal (`duration.isNumeric && duration > .zero`), and a composition track is never added
unless it is successfully populated.

**`events.jsonl` timestamps were wall-clock, not media time.** `RecordingController.elapsed()`
subtracted only `sessionStartTime`, never the accumulated paused duration, while the media files
*are* pause-compacted — so after any pause every marker and screenshot sat ahead of the media
timeline by the total paused time. `RecordingEvent` now carries `media_ts` alongside `ts`, written
from a pause-aware `mediaElapsed(_:)`. `ts` is retained deliberately: wall-clock is a faithful record
of when things really happened. `EventTimeline` recovers media time for logs written before
`media_ts` existed, via `media_ts = ts - sum(resume_ts - pause_ts)` over completed pause spans
preceding `ts`.

**`screen.mov` can contain zero frames.** `ScreenCaptureSession` forwards only `.complete` frames and
sets no maximum frame interval, so a static screen produces long internal gaps — possibly no frames
at all. `ResolvedTimeline` therefore carries base-layer *identity* rather than assuming "screen": with
no screen frames the camera is promoted to full frame, instead of floating over black.

### Frame timing

`sourceTrackIDForFrameTiming` is left at `kCMPersistentTrackID_Invalid` and `frameDuration` fixed at
1/30. Deriving frame timing from the variable-rate screen track is the obvious move and it is wrong:
a static screen produces one sample with a very long duration rather than an empty edit, so the
compositor would emit a single composed frame across that span and freeze the camera PiP with it. A
keyframed overlay over a static base requires a clock independent of the base layer. Output is
therefore CFR 30, and internal screen gaps become desirable — the compositor holds the last decoded
frame, so a static screen simply stays on screen.

### Time mapping

`TimeMap` is hand-rolled and pure rather than reading `AVCompositionTrackSegment.timeMapping`, which
is per-track (the mic's mute gaps are not the screen's), expresses source time including each file's
own edit-list offsets rather than the session clock the transcript uses, silently returns the
*closest* segment on a miss, and only exists on a built non-Sendable composition.

Three properties it commits to from the start: source-to-composition is **one-to-many** (duplicating
a clip maps one source instant to several playhead positions), it can be **empty** (that range was
cut, so the transcript row renders "removed" rather than time 0), and clip intervals are
**half-open** `[start, end)` so a cut boundary belongs to the later clip and does not flicker for a
frame. The canonical timescale is `90_000`; audio trims stay snapped to video frame boundaries in v1
so there is only one timescale in play.

The transcript is derived from `microphone.m4a`, so its timestamps are in mic media time, which is
not necessarily session time. If the mic writer had warm-up latency that file carries a leading empty
edit. Anything reading through AVFoundation's edit list is unaffected by that — but WhisperKit loads
audio with `AVAudioFile(forReading:)` (verified in its own `AudioProcessor.swift:277`), which reads
the raw track and does **not** apply edit lists, so its timestamps start at the first real sample and
are early by exactly that empty edit. `SessionEdit.micTimeOffset` holds that duration, resolved once
from the mic track's first segment, and both the transcript importer and the EDL read it from there
rather than each guessing. Measured on a real session: screen 0.13s, camera 1.02s, microphone 0.0s —
so the correction is usually a no-op, which is exactly why getting its direction wrong would be easy
to miss.

## Session folder

`SessionFolder` gains `load(rootURL:)` — deriving the same fixed filenames `make` produces — so the
review layer never rebuilds paths, plus `editURL`, `transcriptURL`, and the `.peaks` siblings:

```
~/Movies/Aura/<yyyyMMdd-HHmmss>-<hex>/
  screen.mov  camera.mov  microphone.m4a  system-audio.m4a
  microphone.peaks  system-audio.peaks     <- waveform caches, binary
  transcript.json  edit.json  events.jsonl  screenshots/
```

Waveform caches are binary rather than JSON: 180k buckets x 3 floats is ~5 MB of text and ~200 ms to
parse, against a 2.3 MB blob and one `Data(contentsOf:)`. The header carries a magic, a format
version, and the source file's size and mtime; a mismatch on load triggers re-extraction, which is
the entire invalidation story.

## Waveforms

Samples are placed by `presentationTimeStamp`, never by running sample count. This is the one
correctness point in the feature: the mic track has empty edits wherever `append` was skipped during
mute, and `AVAssetReaderTrackOutput` honours the edit list by jumping PTS across the gap rather than
emitting silence. A count-based accumulator would smear the whole waveform leftward by the total
muted duration and desync it from the video. A parallel `coverage` array comes free from the same
pass, so muted spans render as muted rather than as silence.

Extraction streams — mono float32 at 44.1 kHz over 30 minutes is ~317 MB per lane if materialized —
and runs in an `actor` owning the non-Sendable `AVAssetReader`, publishing Sendable chunks so lanes
draw progressively. At 1/100 s buckets a 30-minute lane is ~2.3 MB, so both stay resident and zoom
re-buckets in memory (min-of-mins, max-of-maxes), which is exact rather than a coarser re-decode.
`PeakAccumulator` holds the bucketing arithmetic with no AVFoundation types in its signature.

The two lanes stay two separate composition audio tracks through to export, because
`AVMutableAudioMixInputParameters` is per-track — that is what makes independent gain/mute
expressible at all. Merging them earlier would make a gap in one indistinguishable from silence in
the other.

## A/V synchronisation

The recorded files are **not** self-aligned, and the reason is asymmetric handling in
`AVAssetWriter`. All four writers call `startSession(atSourceTime: sessionStartTime)` with the
same instant, and each capture source then starts producing samples some time later — measured
on a real session: screen +0.13s, camera +1.02s. For **video** the writer preserves that delay
as a leading empty edit, so the content stays where it belongs. For **audio** it does not: the
track has no empty edit and its edit list maps target 0 to the first captured sample, i.e. the
warm-up offset is discarded and the audio plays early by that entire amount. That is the
audible desync, and it is several hundred milliseconds because the microphone starts last —
after four writer setups and the `SCStream`.

Rather than depend on that behaviour, alignment is now explicit. `TrackWriter` records where
its first accepted sample landed (the pause-rebased timestamp, so a pause before the first
sample cannot skew it), and `stop()` writes one `track_start` event per track carrying the
offset from the session start. At review time each track's correction is

    correction = recordedStartOffset - leadingEmptyEdit

which is ~zero for video (the two agree) and the whole offset for audio (the file records
none). `LayerInstructionCompositionBuilder` shifts each track's source range back by its
correction when laying clips down, so the head of an audio track becomes silence — which is
the truth: the microphone was not running yet. Verified end to end: with a recorded mic offset
of 0.4s the built composition's mic track begins with a 0.4s empty edit while the video tracks
begin at zero.

Sessions recorded before `track_start` existed carry no offsets and get no automatic
correction, so `AudioLaneSettings.offset` provides a manual per-lane slip (±5s, 10ms nudges),
exposed in the lane header and available to the agent as `set_lane_offset`. It also covers
residual device latency that nothing can measure. Note the raw files remain externally
misaligned by design — the offsets live in `events.jsonl` and are applied by the composition,
so it is the export, not the source files, that is correct.

## Waveform zoom

`WaveformWindow` (pure) decides which slice of the timeline the lanes draw. The window follows
the playhead rather than carrying its own scroll offset: one control instead of two, and the
playhead can never end up off screen. Zoom bottoms out at 0.25s visible, below which the
1/100s peak buckets read as steps rather than a waveform. Because the cache is stored at that
resolution, zooming never re-reads the audio.

Each column is mapped composition time -> session time -> the lane's own file time (through
`TimeMap` and then the lane offset), so the drawn waveform matches what is actually heard after
both a cut and an A/V slip.

## Windows

`ReviewWindowPresenter` opens review windows with AppKit rather than a SwiftUI `WindowGroup`, for
two reasons specific to a menu-bar app.

The trigger has to work at all. `MenuBarExtra`'s content view exists only while the menu is open,
and `stop()` completes asynchronously — it awaits the capture stream and the writers — *after*
clicking Stop has already dismissed the menu. An `onChange` observer living in that view is
therefore never alive at the moment a session completes, and reopening the menu builds a fresh view
whose observer has no previous value to compare against. So `RecordingController` exposes an
`onSessionCompleted` callback that the app wires once at launch, instead of a published property
that nothing is around to observe.

Teardown has to be deterministic. `ReviewViewModel.close()` must run to remove the player's
periodic time observer (dropping one without removing it is undefined behaviour) and to flush
`edit.json`. `onDisappear` is not reliable for a hosted view when its window closes, so the
presenter owns the view model and tears it down on `willClose`. Windows are keyed by session id, so
asking twice for the same recording focuses the existing window rather than building a second
composition over the same files.

## Transcription

On-device WhisperKit (`transcribe(audioPath:decodeOptions:)` with `DecodingOptions(wordTimestamps:
true)`), model `base`. Models download from Hugging Face on first use and cache outside the repo, so
nothing is committed — the same decision taken for Phase 2. `SessionTranscriber` preserves
`TranscriptionSegment` timing including word timings, which is what later makes "delete this
sentence" a precise operation. It runs off the main actor; the window opens and plays immediately
with the panel showing progress.

This is deliberately *not* the Phase 2 branch's `Voice/Transcriber`, which collapses results to a
joined string and discards all timing.

## Agent edits

`AgentEditPanelView` is where the user asks for a change in words, typed or dictated.
`VoiceInstructionRecorder` captures a short clip with `AVAudioRecorder` and transcribes it with
the same on-device WhisperKit pipeline, so dictation needs no network.

The request goes out over **Agent2Agent** (`POST /a2a/agents/{id}/message:send`), not the
widget endpoints. A2A is the only surface that authenticates with the API key alone; the widget
path additionally needs a visitor token obtained through a browser redirect, which is a poor
fit for a desktop app. It requires Agent2Agent sharing enabled on the agent, and an API key
created with empty allowed origins (a native client sends no `Origin`). The key lives in the
Keychain, the base URL and agent id in `UserDefaults`.

Two pieces carry the weight and are unit-tested accordingly. `EditSuggestionPrompt` states the
operation vocabulary exactly and includes the transcript **shifted into recording time** by
`micTimeOffset` — handing over the microphone's own clock would make every AI-proposed cut land
slightly wrong — plus the current edit state, so suggestions are relative to the edit as it
stands rather than to the original recording. `EditSuggestionParser` reads the reply
defensively, since it is free text from a language model: fenced or bare JSON, an array, an
`{"operations": […]}` wrapper, or a single object, with bracket scanning that ignores string
contents. An operation this build cannot represent is dropped rather than guessed at, and the
valid ones around it survive.

Suggestions are never auto-applied. They stage in a pending list, and accepting one runs
through the same `EditDocumentStore.apply` a mouse drag does — so an AI edit is reviewable
before it lands and undoable after, and the agent has exactly the user's powers and no more.
"Apply All" is one undo step and all-or-nothing.

A future backend improvement would be a `video_edit_suggestions` skill returning
`{"ok": true, "type": "edit_suggestions", "operations": [...]}` read off the existing
`TOOL_CALL_RESULT` SSE frame, following the `html_canvas` precedent — structured output instead
of parsing prose, with no new event type needed.

`PiPStyle` (`cornerRadius`, `borderWidth`, `shadow`) is carried in `ResolvedTimeline` now and ignored
by the layer-instruction builder, so `edit.json`, `EditOperation`, and the UI do not change when a
custom compositor lands — only which builder is constructed.

## Known limitations / follow-ups

- **Aspect-fit only.** The PiP is authored at the camera's own aspect ratio with aspect-locked drag
  handles, which avoids `cropRectangle` entirely and keeps geometry to pure scale-plus-translate.
  This matters more than it sounds: a real session paired a 2560x1440 screen with a 640x480 (4:3)
  camera, so assuming the two share an aspect ratio would have been visibly wrong.
  Aspect-fill needs a golden-frame test first: the SDK specifies the crop rect's coordinate space but
  not whether the cropped region keeps its in-frame offset or re-origins to (0,0).
- **No rounded corners, borders, shadows, or non-rectangular PiP.** The built-in compositor supports
  only affine transform, opacity, and an axis-aligned crop. These need the custom compositor.
- **The agent transport is unverified against a live backend.** The A2A request and reply
  shapes are implemented from the API's contract and covered by unit tests, but nothing here has
  been exercised against a running InnomightLabs instance.
- **Export always re-encodes.** `AVAssetExportPresetPassthrough` ignores `videoComposition`
  entirely, and there is nothing to pass through when two tracks composite into one. The
  document-level fast path (single full-range clip, PiP hidden throughout, unity gain, no mute -> copy
  the file) is not implemented yet. Generational HEVC-to-HEVC loss is visible on screen text; that is
  the trigger to move to the `AVAssetWriter` path, which takes the same composition objects and is
  purely additive.
- `AVAssetExportPresetHEVCHighestQuality` is quality-based rather than fixed-size, but it will not
  scale up and may cap resolution on very large displays. Explicit bitrate control is the same
  `AVAssetWriter` follow-up.
- Trim/cut UI is not built. `SessionEdit.clips` is an ordered EDL and `TimeMap` already handles
  multiple clips, so it is additive.
- The camera aspect discrepancy has an upstream cause worth noting:
  `CameraRecorder.devicePixelSize` read `device.activeFormat` before the input was added, but
  `AVCaptureSession` applies its preset at that point and can change the format. Fixed here with
  `.inputPriority`; regardless, the review layer always derives geometry from the written file's
  `naturalSize` x `preferredTransform` and never trusts the recorder's declared size.

See `/Users/vslala/.claude/plans/scalable-sleeping-russell.md` for the approved plan this was built
from, including the manual verification steps.
