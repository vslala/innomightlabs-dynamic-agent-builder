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

## Word-level editing

The first round of agent editing was imprecise, and the agent diagnosed it itself: "the digest
only provides phrase-level timing, not exact word-level". Reading a real session's files found
four faults behind that.

**Whisper markup was being sent as speech.** All 56 cues in a real recording carried inline
control tokens — `<|startoftranscript|><|en|><|transcribe|><|0.00|> Hey everyone…` — because
cue text came from `segment.text`. The per-word text was clean all along, so cue text is now
rebuilt from the words, and `Transcript.cleaned` strips `<|…|>` from anything else.

**The transcript ran past the end of the video.** A hallucinated `[BLANK_AUDIO]` cue sat at
291.8s on a 265.3s recording, so the agent could propose edits beyond the end. Cues are now
dropped or clamped against the media duration.

**Word timings were available but never sent.** 596 words existed in `transcript.json`;
the digest carried 56 phrases. Words now have stable ids and travel in the digest, so the
agent addresses a word instead of computing a timestamp.

**Rounded times made keyframes unaddressable.** A real `edit.json` held overlay keyframes at
`84.5` and `84.5001`; both render as "84.5" once rounded for the agent, which is why it got
"There is no camera keyframe at 84.50s". Two fixes: keyframes within one frame of each other
are now the same keyframe (the earlier time is kept, so repeated nudges don't make it creep),
and removal matches the nearest keyframe within a frame rather than demanding float equality.

`Transcript` is at schema v2 and a v1 file is **discarded rather than migrated** — its text is
polluted, and re-running the model produces something correct instead of something patched.

### Reversible exclusions

Cutting words is a separate, reversible layer: `SessionEdit.excludedWords` rather than edits to
`clips`. `effectiveClips` subtracts them, so removal is non-destructive and a single word can be
restored later, individually and out of order, by either the user (clicking a struck-through
word) or the agent (`restore_words`). Unwinding one word months later shouldn't mean undoing
everything since.

Each entry stores its resolved span in session time as well as its id, which keeps `edit.json`
self-contained — playback and export never need the transcript — while the id stays the handle
for addressing it.

Filler sweeps are **range-scoped and resolved locally**. The agent emits
`exclude_filler_words{words, from, to}` and Aura finds every instance from the full word list,
then presents them as one reviewable suggestion naming what will go. Aura has the whole
transcript where the agent may have a trimmed view, so it finds instances the agent would
miss; scoping is required because an unscoped sweep removes words that carried meaning.

### The transcript's clock must match the microphone lane's

Word cuts are applied to the timeline, so they are only correct if the transcript and the audio
agree on when a word happens — and they do not, natively.

The transcript is produced by WhisperKit reading the **raw** microphone track, so its zero is
the first captured sample. The composition, meanwhile, shifts the microphone lane later by
`alignmentCorrection` to undo the capture delay (see A/V synchronisation). The conversion
between the two is therefore the *total offset applied to that lane* — the automatic correction
plus any manual slip — and it is computed from the resolved timeline rather than read from the
document, so a stale stored value cannot desync them.

Getting this wrong is silent and looks like the feature not working at all: the word is struck
through in the transcript, the timeline genuinely shortens, and yet the word is still audible
because the cut removed the audio beside it. It shipped that way once, with
`SessionEdit.micTimeOffset` seeded from the microphone's *leading empty edit* — which is always
zero for audio, precisely because `AVAssetWriter` discards it. `WordExclusionIntegrationTests`
now covers document, composition, and view model together, since no single-layer test could
have caught it.

### Word ids are authoritative; spans are a cache

`ExcludedWord` stores both the word id and its resolved span, and the span is **re-derived
from the transcript** whenever one is loaded. The id is the real handle; the span exists only
so `edit.json` can play back without the transcript.

That reconciliation is a repair, not an edit — it does not consume undo history, because the
user never asked for it. It exists because a build that converted transcript times to session
times incorrectly baked 112 wrong spans into a real document, and without self-healing those
would have kept cutting the wrong audio forever. Making the derived value derived again means
this class of bug fixes itself on next open.

### The 32,000-character budget

Treated as a useful constraint rather than something to remove. The digest splits into:

- `outline` — a coarse map of the **whole** recording, cues merged into blocks capped at 60
  regardless of length (blocks widen for a long recording) with text abridged. Bounded by
  construction, because a full phrase-level transcript exceeds the cap on its own and an agent
  that has lost the shape of the recording cannot even ask a sensible question.
- `words` — word-level detail for `[detailFrom, detailTo]`, centred on the playhead, with
  compact keys (`i` id, `s` start, `e` end, `t` text) and a legend in the prompt. Full key
  names would cost ~20 characters per word and put a long recording out of reach.

Each is guaranteed a share of the budget (the outline takes at most 45%) so neither starves the
other, and what was dropped is counted so the agent knows it has a partial view.

When the agent needs detail it does not have, it asks: `request_transcript{from, to}`, which
Aura answers as a follow-up turn in the same conversation, capped at three hops so it cannot
loop. Verified against the live agent, which spontaneously used it.

## Waveform legibility

A linear amplitude axis cannot render speech. Measured on a real recording: peak 0.35
(-9 dBFS), but the **median 10ms bucket peaks at 0.0022** — 0.22% of half-height, which is
sub-pixel. Only the top 1% of buckets exceed 10% of the lane. Drawn linearly it is a flat line
with occasional flecks, and nothing can be edited against it.

Two changes make it readable, both borrowed from Audacity:

**A decibel vertical axis** (`WaveformScale`, the default), mapping -60 dBFS…0 to the lane's
half-height. That same median bucket becomes 12% and peaks reach 85%, so the lane's height is
spent on the range the audio actually occupies. -60 dB is below a normal room's noise floor, so
genuine silence still reads as silence. Linear remains available and the choice persists in
`ReviewPreferences`.

**A peak-plus-RMS envelope.** `WaveformPeaks` now carries per-bucket RMS alongside the
extremes, drawn as a solid inner band under a lighter outer envelope. Peaks alone are spiky and
say little about where speech is; the RMS body is what gives the shape meaning. Reducing for
zoom-out combines RMS quadratically, since averaging RMS values understates loudness. Both are
drawn as filled ribbons with a minimum hairline, so a quiet-but-present stretch still shows as
a line — the distinction between "silent" and "quiet" is exactly what a cut decision turns on.

The peaks cache is at format v2 as a result; a v1 blob is rejected and re-extracted.

## Waveform zoom resolution

The cached envelope is 10ms per bucket, which is ample for the whole recording on screen and
useless up close: a quarter-second window is 25 data points, which draws as a row of steps with
nothing to aim a cut at.

So when the cache is coarser than roughly one bucket per four points of width,
`WaveformExtractor.detail` re-reads **just the visible window** at display resolution — about
one bucket per point, capped at 8,000/s. That is affordable precisely because the window is
short: a quarter-second of mono audio is 11k samples, and `AVAssetReader.timeRange` means only
that much is decoded. Measured on a real recording, a 0.25s window goes from 25 buckets to 600.

Requests are coalesced (the window follows the playhead, so it is asked for constantly during
playback) and the cached envelope keeps drawing until the finer read lands, rather than showing
a torn mixture of the two.

## Camera overlay styling

Shape, border, and shadow need a real compositor: the built-in one offers only an affine
transform, opacity, and an axis-aligned crop. `CoreImagePiPCompositor` provides them, and
`PiPStyle.isPlainRectangle` selects it — the cheaper layer-instruction path stays in place for
an unstyled overlay, and is still the default.

The overlay rect is authoritative: its origin is where the overlay starts. Getting that wrong
is conspicuous — an overlay placed at x = 0 that does not touch the left edge reads as a bug,
and there were two separate causes.

A circle has to be squared off (see below), and squaring was **centred**, which inset the
circle inside a wider rect and left a gap beside it. It is now anchored to the rect's origin.

Separately, the built-in compositor can only place a layer with an affine transform, so it
aspect-**fits** the camera and letterboxes the remainder. That is invisible while the rect
matches the camera's aspect ratio — which the drag handles guarantee — but an agent can send
any rect, and a 4:3 camera fitted into a square-ish rect sits inset with a gap. Rather than
depend on `setCropRectangle`, whose origin semantics the SDK leaves unstated,
`ResolvedTimeline.canUseLayerInstructions` routes an aspect-mismatched overlay to Core Image,
which fills. Correctness by construction; the cheap path still handles the common case.

Two more things only a rendered frame revealed:

- **A circle needs a square.** The overlay rect follows the camera's aspect ratio, so it is
  virtually never square; max-rounding it produced a capsule. `PiPMask.drawnRect` squares to
  the shorter side and centres within the requested rect, and the drag handles use the same
  rect so they still frame what is drawn.
- **Masking has to stay premultiplied.** `CIBlendWithAlphaMask` against an empty background
  leaves masked-out pixels as white with zero alpha, which looks right through a software
  context and composites as opaque white on the GPU path. `CISourceInCompositing` (and
  `CISourceOutCompositing` for the border ring) multiplies through the mask's alpha and is
  correct in both.

`PiPMask` is verified by rendering and reading pixels — the only way to know a circle is round
— and the compositor is verified through a real composition and a real export.

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

`AgentEditPanelView` is the conversation with the agent about this recording, typed or
dictated. `VoiceInstructionRecorder` captures a short clip with `AVAudioRecorder` and
transcribes it with the same on-device WhisperKit pipeline, so dictation needs no network.

### Transport

**Agent2Agent JSON-RPC**, verified against the live service. `POST /a2a/agents/{id}` with
`Authorization: Bearer pk_live_…`; the key alone is sufficient, where the widget conversation
endpoints additionally want a visitor token obtained through a browser redirect — a poor fit
for a desktop app. Requires Agent2Agent sharing enabled on the agent.

Three things about this endpoint are not what its own spec would suggest, and each was found
by trying it:

- Methods are **PascalCase** (`SendMessage`, `GetTask`, `ListTasks`), not the A2A spec's
  `message/send`, which returns `-32601 Unsupported A2A method`.
- `role` is the enum value **`ROLE_USER`**, not `user`.
- JSON-RPC failures arrive with **HTTP 200** and an `error` object, so status codes alone
  never reveal them.

The reply is at `result.task.status.message.parts[].text`. It is decoded from that path
specifically rather than scavenged, because the prompt is echoed back in `history` and is
longer — a "pick the longest text" heuristic would return the question instead of the answer.
Scavenging remains only as a fallback for an unexpected task shape.

Messages are capped at **32,000 characters over at most 16 parts**, which is what bounds the
digest below.

The alternative, `POST /widget/generate-text`, also works with the key alone and was slightly
faster in a single sample (11.7s vs 15.6s — noise at that resolution). It was not chosen
because its conversation key is derived from WordPress-shaped `context.site_url` and
`context.post_id` fields, which would couple Aura to a contract that has nothing to do with it.

### One conversation per recording

`contextId` is A2A's first-class conversation key, and Aura sets it to
`aura-session-<sessionID>` — deterministic from the session id, so it survives app restarts
with nothing persisted. Verified: a follow-up in the same context answered from the earlier
turn without the context being restated.

**Known issue, not solved by A2A:** the agent's long-term memory spans conversations. A
codeword given only in one `contextId` was recalled under a different one, because memory is
scoped to the API key's owner rather than the conversation. Per-recording history works;
per-recording *isolation* does not. The prompt mitigates it by naming the session and telling
the agent to reason only from the digest in front of it, but a real fix belongs in `api/`.

### The digest

`SessionDigest` is the compact, complete description of one recording, sent to the agent as
JSON and written to `digest.json` in the session folder.

Rich, because the agent can only propose sound edits knowing what actually happened: which
tracks exist and how long they are, their recorded start offsets and sync corrections, where
the recording was paused, what the user flagged, which tracks failed, what currently survives
(`keptSpans`), the camera keyframes, the audio lane state, and the transcript.

Compact, because it competes with the instruction for a 32,000-character budget: short keys,
times rounded to centiseconds, zero-valued offsets omitted, and `rect` as a four-element array
rather than an object. A real session came out at **1,035 characters**. When it does not fit,
only the transcript is trimmed — everything else is small, bounded and structural, while a long
recording's transcript is unbounded — and `transcriptCuesOmitted` tells the agent it is not
seeing everything, rather than letting it assume the recording ends early.

Sent as JSON rather than prose because it is unambiguous, and because the same content is
persisted: a suggestion that looks wrong is diagnosed by reading exactly what the agent was
told. Transcript times are shifted into recording time by `micTimeOffset` first — handing over
the microphone's own clock would make every proposed cut land slightly wrong.

### Configuration

The key lives in the **Keychain**; base URL and agent id in `UserDefaults`. A GUI app launched
from Finder inherits no shell environment, so environment variables (`AURA_AGENT_API_KEY`,
`AURA_AGENT_ID`, `AURA_AGENT_BASE_URL`) are honoured only as an override for scripts and tests.

`AgentConnectionCheck` powers "Test Connection" in the settings sheet and answers two different
questions: `/widget/config` needs only the key, so it both proves the key valid and returns the
agent id (the user pastes a key and the id fills itself in); the A2A card then confirms sharing
is actually enabled, which the key alone cannot tell you.

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

- **Word timing is the floor, not character timing.** Whisper reports per-word boundaries and
  nothing finer, and a word is the smallest unit that is audibly sensible to cut — so
  "character-level" control means addressing text, not splitting audio mid-word.
- **Screen capture is native-resolution, not a fixed 4K.** `CaptureTarget.pixelSize` is
  `contentRect x pointPixelScale`, i.e. the display's backing pixels, so a Retina or scaled
  display records at its true framebuffer size. A 1440p panel therefore records 2560x1440
  because that is all there is — the preview's 1600px cap is separate and applies only to
  playback, never to the recording or the export.
- **Overlay handles are hover-only.** They are chrome, not content, so they appear when the
  pointer is over the preview and persist through a drag.
- **Style is not keyframed.** Shape, border, and shadow apply to the whole recording: a camera
  that changes shape partway through reads as a glitch rather than an edit. Position and
  visibility remain keyframed.
- **Aspect-fit only.** The PiP is authored at the camera's own aspect ratio with aspect-locked drag
  handles, which avoids `cropRectangle` entirely and keeps geometry to pure scale-plus-translate.
  This matters more than it sounds: a real session paired a 2560x1440 screen with a 640x480 (4:3)
  camera, so assuming the two share an aspect ratio would have been visibly wrong.
  Aspect-fill needs a golden-frame test first: the SDK specifies the crop rect's coordinate space but
  not whether the cropped region keeps its in-frame offset or re-origins to (0,0).
- **No rounded corners, borders, shadows, or non-rectangular PiP.** The built-in compositor supports
  only affine transform, opacity, and an axis-aligned crop. These need the custom compositor.
- **The agent's memory is not scoped per recording** — see above. Client-side prompting
  mitigates, but the fix belongs in `api/`.
- **Always-on wake-word detection is behind `FeatureFlags.isWakeWordListenerEnabled`, off.**
  It held the microphone open for the life of the app while nothing downstream consumed a
  detection, so the privacy cost bought nothing. With it off Aura touches the microphone only
  during a recording and while dictating. The CoreML models are lazily loaded, so the flag
  being off means they are never even read.
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
