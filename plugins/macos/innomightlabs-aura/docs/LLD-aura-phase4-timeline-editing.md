# LLD: Aura Phase 4 — Timeline Editing

Follows [LLD-aura-phase3-review-editor.md](LLD-aura-phase3-review-editor.md). Adds selection,
manual markers, splits, visible cut regions, and word-level playback highlighting — and
restructures the edit document so that keeping all of those in sync is a property of the
design rather than something each surface has to remember.

## Context

Phase 3 can cut words and ranges, but the result is invisible: a cut leaves no mark on the
waveform, so there is nothing to review, select, or restore. The asks were: markers showing
cut areas (colour-matched to word deletions), word-level highlighting during playback, manual
markers, deleting a selected waveform region, splitting into parts — all staying in sync with
video, audio, and subtitles.

The sync requirement is the design driver. An audit found **14 distinct places** converting
between the three clocks (composition / session / transcript), plus 3 more independently
composing the per-lane file→session offset. That arrangement has now produced **three** bugs:

1. `events.jsonl` markers placed on the wall-clock rather than the media clock.
2. Word cuts landing beside the words they named, because the transcript's clock was seeded
   from the microphone's leading empty edit — which is always zero for audio.
3. **Found during this design and still live**: `ReviewViewModel.requestWaveformDetail`
   converts the viewport from composition time to file time by subtracting only the lane
   offset, with no time-map step (`ReviewViewModel.swift:452-466`), while
   `WaveformTrace.columns` indexes those buckets from a *composition*-time origin
   (`WaveformLanesView.swift:235, 360-366`). Once anything is cut, source runs ahead of
   composition, so the read fetches the wrong region and every column falls outside
   `bucketCount`. On a 112-cut document, zoomed waveform detail draws **nothing**, silently.

Three instances of one class of bug is a design signal, not bad luck.

## The shape of the fix

**One declarative document; everything else derived; one place that knows the clocks.**

```
SessionEdit (declarative, persisted)          ← the only writable state
  recordingDuration, cuts[], splitPoints[], markers[],
  cameraOverlay, audioLanes, cameraStyle, micTimeOffset, transcriptIdentity
        │  EditOperation (command)                  ← the only way to mutate
        ▼
  derived: clips  =  [0, recordingDuration] − merged(cuts)
        │  TimelineResolver (pure)
        ▼
  ResolvedTimeline  (+ TimeMap, lane offsets, render size)
        │  ReviewProjector.project(timeline:document:transcript:events:)   ← PURE, the ONLY clock authority
        ▼
  ReviewProjection   regions[] words[] cues[] markers[]   + conversion queries
        ▼
  Views: pure functions of (projection, playhead, selection, viewport). No clock math.
```

Patterns, and what each buys:

- **Declarative write model.** Cuts are a set of facts about the original recording, not
  mutations of a clip list. Every cut is addressable by id and individually restorable —
  which is what makes "click a cut region to bring it back" possible at all.
- **Command** (`EditOperation`) — already in place; gives undo, agent parity, and one
  validation point.
- **Derived read model** (CQRS-lite). `ReviewProjection` is computed once per edit and holds
  pre-reconciled values. Adding a surface cannot desync it, because a surface has nothing to
  convert.
- **Value semantics** throughout, so projections are cheap to diff and trivial to test.
- **Transient UI state** (selection, viewport, playhead) deliberately outside the document:
  it must not persist, must not be undoable, and must not invalidate the composition.

## Document restructure

```swift
struct SessionEdit {
    var schemaVersion: Int            // 2
    var recordingDuration: TimeInterval
    var cuts: [Cut]
    var splitPoints: [TimeInterval]
    var markers: [EditMarker]
    var micTimeOffset, cameraOverlay, audioLanes, cameraStyle   // unchanged
    var transcriptIdentity: String?   // see "word cuts survive re-transcription"

    var clips: [TimelineClip] { /* derived */ }
}

struct Cut: Identifiable { let id: UUID; var span: TimeSpan; var origin: Origin }
enum Cut.Origin { case range, word(id: Int, text: String), filler(word: String), agent(reason: String) }
struct EditMarker: Identifiable { let id: UUID; var at: TimeInterval; var label: String }
```

`recordingDuration` is **stored, not derived from probes.** Three call sites need the
recording's extent and have no probes: `SessionEdit.applying(_:)` (pure by design, and where
the "would remove everything" guards live), `SessionDigest.make`, and
`EditSuggestionPrompt.build` (which passes `probes: []`). Worse, `probes.map(\.duration).max()`
is *not stable across opens* — `SourceTrackProbe.probe` returns nil for a moved or truncated
file, so deleting `system-audio.m4a` would silently shorten the timeline. Stored clips are
immune to that today and that immunity must not be given up for 8 bytes.

### Deriving clips

```
1. snap every endpoint through Timeline.time(seconds:)   // same grid as EditOperation.snapped
2. base = [0, recordingDuration]
3. normalise cuts: drop non-finite / zero-length / inverted; clamp to [0, D];
   sort by (start, end); sweep-merge where next.start <= current.end   // <=, so adjacent merge
4. subtract merged cuts from base in one two-pointer sweep              // O(n+m)
5. drop zero-duration results
```

**Cuts are merged only in the derivation, never in the document.** Merging them in an
operation would destroy the individual restorability that is the entire point. Two cuts can
legitimately cover the same region — the migration guarantees it, since a v1 word exclusion
inside a coarse gap becomes a real cut — so `ReviewProjection.region(atSource:)` carries
`cutIDs` **plural**, and restoring a region removes all of them. Otherwise the user clicks a
shaded region, one cut is removed, and nothing visibly changes.

Derived clips are now guaranteed source-monotonic, which is what licenses the two-pointer
joins below. `LayerInstructionCompositionBuilder` currently documents the opposite
("clips need not be in ascending source order", `:87-88`); that allowance is removed and the
invariant asserted instead.

**`splitPoints` must not reach `TimeMap`.** Nothing moves, trims or reorders clips yet, so a
split that removes nothing would add a composition segment, an extra `insertTimeRange` per
track, and extra instruction boundaries — for byte-identical output, except that each extra
boundary is another place AVFoundation picks the nearest decodable frame, so a no-op split can
visibly duplicate or drop a frame. `TimeMap` is therefore built from **cuts only**; splits stay
an editing concern until trim or move lands, and they are what the ruler draws (see below).

`TimelineClip.id` is deleted along with `TimeMap.Segment.clipID`: it is write-only today (set
at `TimeMap.swift:35`, discarded by both callers), and regenerated UUIDs would make
`TimeMap == TimeMap` false for identical timelines, defeating the `.equatable()` short-circuit
that stops `WaveformTrace` re-rasterising on every publish.

## ReviewProjection

```swift
struct ReviewProjection: Equatable, Sendable {
    let timeline: ResolvedTimeline        // held, not copied — two maps is two things that can disagree
    let recording: TimeSpan               // source
    let edited: TimeSpan                  // composition
    let regions: [Region]                 // kept | cut(origin, cutIDs) — SOURCE time, for shading
    let words: [ProjectedWord]            // source span + composition spans + isCut + cue id
    let cues: [ProjectedCue]
    let markers: [ProjectedMarker]        // kind: .recording (fact) | .editorial (movable)

    func sourceTime(forComposition:) / compositionTime(forSource:)
    func compositionTime(atCutBoundary:) / word(atComposition:) / region(atSource:)
    func audioFileTime(forSource:lane:)
}
```

Built by `ReviewProjector.project(timeline:document:transcript:events:)` — note **timeline,
not probes**: taking probes would force the projector to recompute
`probe.alignmentCorrection + document.offset(for: lane)`, which is conversion site #15, added
by the change meant to remove them.

Built with **two-pointer merge joins**, not repeated `compositionSpans(forSource:)` calls.
Words are sorted by start and derived segments are source-monotonic, so the join is
630 + 114 steps (~20 µs). The naive version is 630 × 114 = 71,820 `CMTimeRangeGetIntersection`
calls plus an array allocation each: 3–6 ms release, 30–60 ms Debug — a visible hitch on every
edit, in the configuration we develop in.

The projection **must not depend on the playhead**, which ticks 30×/s. Active word and cue are
*queries* on the projection, published behind change-gates in the manner of the existing
`activeCueID` (`ReviewViewModel.swift:269-273`), never called from a view `body`.

It is computed and published **at the same instant as `ResolvedTimeline`** — after
`builder.build` succeeds (`ReviewViewModel.swift:224`). Publishing from the `$document` sink
instead would leave tens of milliseconds where the waveform shows new cuts while the player is
still on the old composition: a fresh instance of the bug class being removed.

## Waveform on the source axis

The lane draws the **whole recording, to scale**, with cut regions shaded in the same colour as
a struck-through word (one `ReviewPalette.cut` token, so "markers match the word deletion
colour" is true by construction rather than by coincidence).

**The viewport does not follow the playhead.** A proportional source axis means the playhead
teleports over every cut — on the real document, 113 jumps across ~387 s of playback, one every
3.4 s. With `WaveformWindow.span` centring on the playhead that would pan the entire waveform
113 times, and each pan triggers `requestWaveformDetail` → a fresh `AVAssetReader` per lane:
~226 reader spin-ups per playthrough. Decoupling the viewport removes the panning and the
thrash entirely; the playhead still jumps (inherent to a to-scale source axis) and can leave
the window during playback, which is the accepted trade.

Consequences to handle:

- All six zoom sites (`visibleSpan`, `canZoomIn/Out`, `zoomIn/Out`, `setZoom`,
  `ReviewViewModel.swift:361-399`) currently read composition duration and must read
  `recordingDuration`, or zoom-out clamps at 387 s and the last 35 s becomes unreachable.
- Clicking inside a cut region seeks to that cut's boundary. Naively that is undefined:
  `compositionTimes(forSource:)` returns `[]` inside a cut, **and also at `cut.span.start`**,
  because ranges are half-open and the cut's start is the exclusive end of the preceding clip.
  The projection exposes `compositionTime(atCutBoundary:)` for exactly this, so the trap is
  solved once rather than per caller — the same hack already lurks in
  `TimelineRulerView.swift:87-90` for end-markers.
- Single click **selects** a cut region; double click **restores** it. Restoring on a single
  click would let a scrub accidentally un-cut a 40-second range with nothing but a shade
  changing to show it.
- `TimelineRulerView.clipBoundaries()` emits one tick per segment start — 113 ticks over
  ~700 pt is a grey smear, and `ForEach(id: \.self)` over `Double` drops duplicates with a
  runtime log. The ruler draws **splits and markers** (few, user-meaningful); cut stitches
  belong to the lane.

Selection is a **source-time span** in the view model, never the document. Cutting it creates
one new `Cut` over the whole span without merging into existing cuts, so un-cutting it
re-exposes what was underneath. Un-cutting is all-or-nothing per cut id: partially un-cutting a
`.word` cut would degrade it to `.range` and destroy the word identity that self-healing
depends on, so it is refused. A selection shows **both** its source span and its kept duration,
since after cuts they differ and the user will otherwise mis-estimate.

## Keeping the clocks honest

Two mechanisms, because policing has failed three times:

1. **Phantom-typed stamps** for every time value crossing into a view:
   `Stamp<Composition>`, `Stamp<Source>`, `Stamp<MicMedia>` — arithmetic defined only within
   one clock, conversions existing *solely* as methods on `ReviewProjection`. A view cannot
   convert one to another because there is no operator to call. Raw `CMTime` stays inside
   `TimeMap` and the composition builder, where it belongs.
2. **Views take the projection, not the view model.** Every Review view accepts a
   `ReviewProjection` plus primitives instead of `@ObservedObject var viewModel`. A view that
   needs raw clock data then fails to *compile*, and the project gets its first view tests and
   SwiftUI previews as a side effect.

A grep test was considered and rejected: it fails today, matches comments in a deliberately
comment-dense codebase, uses a glob that misses `WaveformCanvas`/`WaveformTrace`, and cannot
catch untyped arithmetic like `playhead - segment.start` — which is the form the real bugs
took.

## Word cuts must survive re-transcription

`Transcript.normalized` renumbers word ids densely per file, and `retryTranscription()`
rewrites `transcript.json`. After a retry every `.word(id, text)` cut points at a different
word — and `reconcileExcludedWords`, the self-healing repair, would then rewrite cut spans onto
the *wrong* words, turning a safety net into a corruption mechanism.

So the document stores a `transcriptIdentity` (a hash, in the manner of `PeaksCache`'s
source-stamp). On mismatch: keep the stored spans, degrade `.word` origins to `.range`, tell
the user — and do **not** reconcile.

## Staging

1. **Document + migration.** v2 schema, derived clips, normalisation, operations, guards.
   No UI change. Fully unit-tested, including `migrated.timeMap.duration == v1.timeMap.duration`.
2. **Projection + phantom clocks.** Fixes the live detail-request bug as a side effect.
3. **Source-axis waveform**: cut shading, click/double-click, selection, delete, split.
4. **Markers** (editorial vs recording) and **word-level highlighting**.
5. **Agent**: digest and prompt together.

### Migration (v1 → v2)

Two-stage, and **not** in `Decodable`. Today's decoder defaults missing keys on purpose so
pre-`excludedWords` documents still load; if one struct decodes both shapes, a v2 document that
somehow lacks `cuts` decodes as "no cuts" and **wipes every edit**. So: a separate
`SessionEditV1` mirror, a `SessionEdit.migrating(v1:recordingDuration:)`, and a v2 decoder that
*requires* `cuts` and `recordingDuration`, dispatched on `schemaVersion` before decoding.

```
leading / interior / TRAILING gaps between v1 clips  →  Cut(.range)
adjacent clip boundaries (clips[i].end == clips[i+1].start) →  splitPoints
each ExcludedWord                                     →  Cut(.word(id, text))
```

The trailing gap is the one that gets forgotten, and omitting it lengthens the timeline and
shifts resume positions. Adjacent boundaries must become splits or every split a user ever made
silently vanishes. `micTimeOffset` must **not** be re-applied — v1 `ExcludedWord` spans are
already in session time, and with `micTimeOffset: 0` on the real document a double-application
would not show up in testing. `edit.json` is backed up to `edit.json.v1.bak` before the first
write, because `repair` already schedules a save within 400 ms of opening a window.

### Also fixed in passing

- `EditDocumentStore.apply` pushes an undo step unconditionally, so a no-op operation leaves a
  dead entry: add `guard updated != document`.
- `reconcileExcludedWords`' threshold of `0.0005` is ~45× looser than one tick (1/90000), so it
  can oscillate between neighbouring ticks and rebuild the composition indefinitely. Snap both
  sides and compare exactly.
- `SessionEdit.overlay(at:)` is documented as taking composition time; every caller passes
  session time. Stale comment, latent trap — corrected.
- `TranscriptPanelView.swift:108` renders composition time normally but falls back to
  *transcript* time for a fully-cut cue: two clocks in one column.
- Keyboard handling: the window is an `NSHostingView` in a bare `NSWindow` with no `.commands`
  scene, and `.keyboardShortcut(.space, modifiers: [])` is registered window-wide while the
  agent panel holds a `TextField` — so typing a space into the prompt may be swallowed. Replace
  scattered shortcuts with **one** `NSEvent` local monitor in `ReviewWindowPresenter`,
  consulting a pure `(key, modifiers, focus) -> ReviewKeyCommand?` table.
- Two marker systems now coexist: `events.jsonl` markers are immutable *facts*; document
  markers are *editorial*. `ProjectedMarker.kind` distinguishes them and move/rename on a
  recording marker is rejected rather than silently forked.
- `SessionDigest.keptSpans` is `document.clips`, which becomes 114 spans (~3.5 kB of a 32,000
  budget, reclaimable only from `outline`/`words`) and is un-reasonable-about for the agent.
  It stays coarse — base minus `.range`/`.agent` cuts only — with `excludedWordIds` as the word
  channel. Digest schema version and prompt text change in the same commit.

## What shipped

All five stages landed. Deviations and additions worth recording:

**Keyboard.** `.keyboardShortcut` was replaced by `ReviewKeyCommand` — a pure
`(characters, keyCode, modifiers, focus) -> ReviewKeyCommand?` table — dispatched from one
`NSEvent` local monitor in `ReviewWindowPresenter`. Three reasons the declarative form did not
work here: the window is an `NSHostingView` in a bare `NSWindow` with no `commands` scene to
hang a menu on; a shortcut attached to a conditionally-present button silently does not exist
while that button is hidden; and an unmodified window-wide shortcut is resolved ahead of the
field editor, so `.keyboardShortcut(.space, modifiers: [])` swallowed spaces typed into the
agent prompt. The table takes focus as an input so a bare keystroke is only ever a command when
a text field does not have it, and returns the event unconsumed when a command declines to act.

**Agent prompt overhead is measured, not declared.** `overheadAllowance = 4_000` was a constant
that the Phase 4 vocabulary immediately invalidated — the prompt overflowed the 32,000-char cap,
which the server rejects outright rather than truncating. The template is now rendered with an
empty digest to measure itself (`EditSuggestionPrompt.overhead(request:)`), so the digest's
budget shrinks automatically as the vocabulary grows.

**The digest gained `rangeCuts`, `splits`, and `editMarkers`.** `uncut`, `remove_split`, and the
marker operations are unusable without the handles they name. `rangeCuts` carries an `origin`
tag so the agent can tell its own edits from the user's. Verified against the real 121-word-cut
document: the whole prompt lands at 31,981 of 32,000 characters, the digest having been trimmed
to fit by binary search.

**The digest's new lists are capped.** `fitting(characterBudget:)` can only shrink `outline`
and `words`, so any other list has to be bounded at construction or the digest overflows the
cap with no way to recover. A filler sweep is the realistic trigger: it mints hundreds of cuts
at once, each carrying a 36-character UUID. `rangeCuts` is capped at 40 selected **longest
first** — a stray 12-second cut matters more than the 61st "um" — then re-sorted by time for
reading, with `rangeCutsOmitted` telling the agent the list is partial so it does not conclude
nothing else is cut.

**The decoder accepts synonyms.** The prompt documents one shape per operation, but a language
model reaches for `at` where the enum says `t`, and `ids` where it says `cutIds`. Losing an
entire operation to a synonym is worse than accepting one, so `addMarker`/`moveMarker`/`uncut`
decode either spelling. `AgentOperationVocabularyTests` decodes a concrete instance of every
shape the prompt promises, which is the guard against the prompt and the decoder drifting apart.

**`transcriptIdentity` is an FNV-1a hash, deliberately not `Hasher`.** Swift seeds `Hasher` per
process, so a `hashValue`-derived identity would differ on every launch and detach every word
cut from a transcript that had not changed. It is quantised to milliseconds so a re-serialised
transcript compares equal, and keyed on engine as well, since a larger model resegments.

**A fourth clock was hiding in the waveform.** `WaveformTrace.peaksStart` was a bare
`TimeInterval` carrying a lane's *audio-file* time, and the two call-site branches fed it values
from different clocks — one of them sign-flipped. `laneOffsets` is documented as seconds to
**add** to file time to reach source time, so bucket 0 sits at `+laneOffset`; the view passed
`-laneOffset`, drawing the cached envelope shifted left by twice the offset and disagreeing with
the zoomed detail path, which was correct. On the real session that is a 0.82s displacement. The
fix is structural: `peaksStart` is now a `Stamp<Source>` and the call site derives it from a new
`ReviewProjection.sourceTime(forAudioFile:lane:)` rather than negating by hand. This is the
fourth instance of the bug class the phase set out to eliminate, and it was reachable precisely
because the value crossed into a view untyped.

**Every clock conversion is now inside `ReviewProjection`.** Closing the remaining three took
removing `ReviewViewModel.compositionSpans(for:)` (the projection already computes cue spans)
and routing `playheadSourceTime` and `transcriptTime(forComposition:)` through the projection
instead of reaching into `timeMap`. `grep -rn 'timeMap\.(sourceTime|compositionTime|compositionSpans)'`
over `Sources/Aura` now matches nothing outside `Projection/` and `Composition/TimeMap`.

**Views still take `@ObservedObject`, not a projection.** The second enforcement mechanism was
not adopted. The phantom types turned out to carry the weight on their own: an audit of every
Review view found the type system holding everywhere a `Stamp` was in play, with the single hole
being the untyped `peaksStart` above — now typed. Views also need to *command* the view model,
so a projection-only signature would have required threading a command sink through five views
for no additional protection. Revisit only if a fifth instance appears.

### Gesture layering, learned the hard way

Three separate bugs in this phase came from the same SwiftUI rule: **a descendant's gesture
outranks an ancestor's `.gesture`**, and a gesture that fails is not replayed to the parent.

- A transparent "wider hit target" rectangle carrying `TapGesture(count: 2)` was added inside
  each cut region so a 2pt hairline could be double-clicked. Because it sat under the canvas's
  drag gesture, it consumed *all* input over every cut region: single-click selection stopped
  working, which silently orphaned `selectedCutRegionID` — its only writer — and with it the
  toolbar's Restore button and `restoreSelectedCutRegion()`. A selection drag could no longer
  be started inside a cut either. Cut regions are now `.allowsHitTesting(false)`, and the
  canvas carries a `SpatialTapGesture(count: 2)` as a `.simultaneousGesture`: spatial because
  restoring needs to know *which* cut was clicked, simultaneous so single clicks still reach
  the drag.
- The same overlay had subtly wrong geometry regardless: `.overlay` applied after `.offset`
  does not inherit the offset, so for narrow cuts the target sat several points left of the
  hairline it was meant to cover — missing exactly the case it was added for.
- Marker glyphs on the ruler used `.onTapGesture`, punching a 14pt dead zone into the scrub bar
  at every marker. Now `.simultaneousGesture(TapGesture())`.

And one from a related habit: `markerDrag` was attached to the 9pt marker glyph but read
`value.location.x`, which `DragGesture` reports in its own `.local` space. Divided by the canvas
width, every drag resolved to within a fraction of a percent of the window's left edge — and
since the view's position was recomputed from the live stamp, it oscillated under the cursor.
It now uses `translation`, which is a delta and therefore independent of which view the gesture
hangs on.

### Two commit conditions that must not be conflated

`EditDocumentStore.repair` aborts if its closure returns `false`, *and* independently drops a
transform that produced an equal document. The reconcile closure returned "did a word cut's
span move", which also discarded the `transcriptIdentity` stamp it had just written — so on
every document whose spans were already correct, including every freshly migrated v1 document,
the identity stayed `nil`. The mismatch guard could then never fire, and the re-transcription
protection this phase added was permanently disarmed while appearing to be present. It is
data-dependent, so it would have looked intermittent. The closure now returns `true`
unconditionally and lets the store's equality check decide.

### Keyboard: Cmd+Z is not a safe chord

The key table let all command chords through while a text field had focus, on the reasoning
that modified keys are unambiguous. Cmd+Z is the exception: a text field owns it for its own
editing, so undoing a typo in the agent composer instead undid the last timeline edit — and
the typed text was unrecoverable. Undo and redo now decline when focus is `.textInput`; zoom,
which means nothing in a text field, still resolves.

## Verification

1. `./scripts/test.sh` — including the migration duration-equality test and projection joins.
2. Open the pre-existing 112-cut document: edits intact, timeline duration unchanged to within
   one tick, `edit.json.v1.bak` written.
3. Zoom to 0.5 s on that document and confirm the detail waveform **draws** (it currently does
   not).
4. Select a waveform region, delete it: the video cuts, the audio cuts, the affected words show
   struck through, and the region shades — one undo reverses all of it.
5. Double-click a cut region: it restores, and the words inside un-strike.
6. Play: the highlighted word tracks the audio, and the viewport does not pan.
7. Add, rename, move and delete an editorial marker; confirm a recording marker refuses to move.
8. Export and confirm the file matches the preview.
