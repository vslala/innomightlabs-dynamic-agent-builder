# Aura Phase 5 — Studio UI

## Context

Phases 3 and 4 built a correct editor: one declarative document, one projection that owns every
clock conversion, cuts visible on a source-axis waveform, word-level transcript editing, and an
agent that emits the same operations the UI does. What it looks like is a developer tool — an
`HSplitView` with a preview on the left, two stacked panels on the right, and a waveform strip
at the bottom, all in system chrome.

This phase replaces the shell. The target is an AI-first editor in the manner of Descript or
Screen Studio: the preview dominates, most editing happens through the transcript and typed
commands, and the timeline stays powerful but quiet.

The decision that shapes everything: **the timeline is not a generic NLE.** Aura created the
recording, so it knows there are exactly five lanes — Captions, Screen, Camera, Voice, System
Audio — and it can name them. Nothing here needs "Video 1".

### Scope, as agreed

In: the design system, the window chrome, the three-pane + timeline layout, the header, the
left navigation, preview subtitles, the captions lane, thumbnail filmstrips for Screen and
Camera, the redesigned AI panel with its suggested actions, the command palette, and the
expanded keyboard.

Out, deliberately: side-by-side layout (needs a second base-layer transform in the compositor),
audio noise reduction (a DSP project with no existing foundation), and burned-in captions
(revisit once the styling settles — burned-in captions cannot be turned off later).

`Clean audio` therefore appears in the AI panel as **visibly unavailable** rather than as a
button that silently does nothing.

## Design system

`Review/Theme/AuraTheme.swift`, with a `Color(hex:)` initialiser in `Color+Hex.swift`.

| Token | Value |
| --- | --- |
| `background` | `#0B0D12` |
| `surface` | `#12151C` |
| `surfaceElevated` | `#181C25` |
| `border` | `white @ 8%` |
| `textPrimary` | `#F5F7FA` |
| `textSecondary` | `#9CA3AF` |
| `accent` | `#7C5CFC` |
| `accentHover` | `#8B6CFF` |
| `danger` | `#EF4444` |

Spacing is an 8px system (`xs 4`, `sm 8`, `md 16`, `lg 24`, `xl 32`); radii are 8–12.

Two rules the code must hold to, because they are the ones that decay:

- **No gradients.** One accent, used only where attention is genuinely wanted: the Export
  button, the active nav item, the playhead, the selection, and the AI panel's primary control.
  Everything else is surface elevation and spacing.
- **`ReviewPalette` keeps its meanings but re-points at the theme.** `cut` becomes `danger`,
  which preserves the property established in Phase 4 — a cut region on the waveform is the
  same colour as a struck-through word — while removing the second colour vocabulary.

The window forces dark appearance (`NSAppearance(named: .darkAqua)`) rather than following the
system. These are exact values chosen against a dark ground; honouring a light system theme
would mean designing and maintaining a second palette for a media editor that has no use for
one.

## Window chrome

`ReviewWindowPresenter` gains `titlebarAppearsTransparent = true`,
`titleVisibility = .hidden`, and `.fullSizeContentView` in the style mask, so the traffic
lights float over the custom header. The header reserves 78pt of leading padding for them.

## Layout

```
┌────────────────────────────────────────────────────────────────────┐
│ Header   ·  session name ▾  ·  badge          undo redo  [Export] │
├──────────┬──────────────────────────────────┬──────────────────────┤
│ Sidebar  │          Video Preview           │  AI  |  Transcript  │
│  64–200  │        (majority of area)        │        320–420       │
│          │   subtitles inside safe area     │                      │
│          ├──────────────────────────────────┤                      │
│          │  ◁  ▶  ▷    01:24 / 08:32   ⚙︎   │                      │
├──────────┴──────────────────────────────────┴──────────────────────┤
│ Timeline — 32% of editor height                                    │
└────────────────────────────────────────────────────────────────────┘
```

The timeline is a fixed fraction (32%) of the window height rather than a fixed point height,
clamped to `[220, 420]`, so the preview keeps the majority of the area at any window size.

`ReviewWindowView` becomes the shell and holds no editing logic. New files:

```
Review/Theme/{AuraTheme,Color+Hex}.swift
Review/Studio/{StudioHeaderView,StudioSidebarView,StudioSection}.swift
Review/Studio/{CommandPalette,CommandPaletteView}.swift
Review/Preview/{PreviewStageView,PreviewControlsView,SubtitleOverlayView,LayoutMode}.swift
Review/Timeline/{TimelineView,TimelineLane,CaptionLaneView,FilmstripLaneView}.swift
Review/Filmstrip/{Filmstrip,FilmstripExtractor,FilmstripCache}.swift
Review/Captions/{CaptionCue,SubtitleFile}.swift
Review/Silence/SilenceDetector.swift
Review/Agent/StudioAction.swift
```

## Left navigation

Four items plus Settings at the bottom, as a `StudioSection` enum. Honest about what exists:

| Item | Behaviour |
| --- | --- |
| Library | Disabled, with a tooltip saying it is not built |
| Sessions | Disabled, same |
| Transcript | Selects the right panel's Transcript tab |
| Export | Runs the existing export flow |
| Settings | Opens the agent settings sheet |

Library and Sessions render at reduced opacity and do not respond, rather than dead-clicking.
A session browser is genuinely wanted — recordings currently have to be deleted by hand — but
it is a feature, not chrome, and belongs in its own phase.

## Preview

`PreviewStageView` owns the video, the camera handles, and the subtitle overlay. The three are
positioned against the **fitted video rect**, not the container: `AVPlayerLayer` letterboxes
under `resizeAspect`, and placing a subtitle against the container would drift it off the
picture as the window aspect changes. The rect is computed from `timeline.renderSize`, the same
input `CameraOverlayView` already uses.

Controls are quiet: they sit on `surface` with no borders, and the resolution / speed /
fullscreen group appears only on hover. Transport is previous / play-pause / next, with
`01:24 / 08:32` in monospace.

### Subtitles

Bottom-centre, 9% above the video rect's lower edge, max two lines, `textPrimary` on a 62%-black
rounded container. The text comes from the projection's cues at the current composition time, so
a cue that has been cut simply does not appear — no separate bookkeeping.

### Layout modes

`LayoutMode` — `screenOnly`, `cameraOnly`, `screenAndCamera` — expressed entirely as
`setOverlayKeyframe` operations, so the compositor is untouched:

- `screenOnly` → `visible: false`
- `cameraOnly` → `rect: (0, 0, 1, 1)`, `visible: true` (the Core Image path fills, so this
  covers the screen)
- `screenAndCamera` → the default PiP rect, `visible: true`

Reached through a small layout button and the command palette, never a permanent toolbar. Like
every other overlay change these are keyframed, so a mode switch takes effect from the playhead
onwards rather than retroactively.

## Timeline

Five named lanes, Captions directly above Screen:

| Lane | Visual |
| --- | --- |
| Captions | Compact text blocks, one per transcript cue |
| Screen | Thumbnail filmstrip |
| Camera | Thumbnail filmstrip |
| Voice | Waveform |
| System Audio | Waveform |

All five share the Phase 4 source axis, the same window, the same cut shading, and the same
playhead. That is not a styling choice: a lane on a different axis could not show a cut, which
is the whole reason the waveform moved to the source axis in Phase 4.

Caption blocks are selectable and seek to their cue. Clicking one is the same code path as
clicking a transcript line.

### Filmstrips

`AVAssetImageGenerator.images(for:)` (macOS 14+, and the deployment target is 15) with
`maximumSize` 160×90 and `requestedTimeToleranceBefore/After = .positiveInfinity` — nearest
keyframe is correct for a filmstrip and enormously faster than exact seeks on a long HEVC
screen capture.

Cached as **one binary blob per track**, following the `.peaks` precedent for the same reasons
(one `Data(contentsOf:)`, no parse): magic, format version, source file size and mtime, frame
size, frame count, then an index of `(offset, length)` pairs followed by concatenated JPEG data.
Validated against the source on load, re-extracted on mismatch — that is the entire
invalidation story. Encode/decode is a pure `Data <-> Filmstrip` pair so it tests without the
filesystem.

Frames are decoded lazily for what is visible, behind a small LRU, because the blob holds up to
600 frames and decoding all of them to draw 40 would be wasteful. Density targets one frame per
2s, clamped to `[1s, …]` and a 600-frame ceiling, which bounds both extraction time and cache
size for a long recording.

Not a sprite sheet: 600 frames at 160px is a 96,000px-wide image, past what can be decoded as
one texture.

## AI panel

Two tabs, AI default. Heading "Ask Aura", a prompt field, then suggested actions as cards.

`StudioAction` maps each card to what actually happens, which is the point of the phase — the
agent must change editor state, not produce a disconnected answer:

| Action | Implementation |
| --- | --- |
| Remove silences | **Local and deterministic.** `SilenceDetector` over the Voice lane's peaks |
| Remove filler words | **Local.** The existing filler sweep |
| Generate captions | **Local.** Enables the caption overlay and lane; export writes a sidecar |
| Create highlights | A crafted prompt to the agent |
| Shorten video | A crafted prompt to the agent |
| Clean audio | Unavailable, and says so |

A card that runs locally produces exactly one undoable operation, so one Cmd+Z reverses it.

### Silence detection

Pure: `[Double] (bucket RMS) -> [TimeSpan]`, so it tests without audio. Speech below a dB floor
(default −40 dBFS) for longer than a minimum run (default 0.35s), with 0.1s of padding kept at
each end so the cut does not clip the attack of the next word. Bucket indices become source
times through `ReviewProjection.sourceTime(forAudioFile:lane:)` — never by hand, which is how
Phase 4's last bug happened.

This needs a new batch operation, `removeRanges([TimeSpan])`. Applying N single cuts would put
N entries on the undo stack, and "remove silences" must be one step.

## Command palette

Cmd+K. A search field over a `CommandPalette` registry — id, title, subtitle, keywords,
shortcut, availability, action — filtered by subsequence match on title and keywords. Arrow
keys move, Enter runs, Escape closes.

The registry is a pure value, so the palette's contents are testable without a window, and the
same list feeds the keyboard table's discoverability (every palette row shows its shortcut).

Commands: remove silences, remove filler words, generate captions, create highlight, split at
playhead, delete selection, add marker, the three layout modes, export, open transcript, zoom
in/out/fit.

## Keyboard

`ReviewKeyCommand` already centralises this and gains the spec's bindings. Two honest
deviations, both consequences of the document model:

- **`Shift+Delete` (ripple delete) and `Delete` do the same thing.** Aura's timeline is derived
  from cuts and cannot contain a gap, so "lift" — delete leaving a hole — is not expressible.
  Mapping both to the same ripple delete is truthful; adding a lift would mean a second
  timeline model.
- **`B` is a blade *mode*, not an immediate cut.** Pressing it arms the next timeline click to
  split there; Escape disarms. `Cmd+B` splits at the playhead immediately.

`I` / `O` set the selection's in and out points, reusing the Phase 4 selection rather than
introducing a second range concept. `J`/`K`/`L` set rate −1 / 0 / +1, with repeated `J`/`L`
stepping through 2x and 4x as in an NLE.

## Session naming

The header shows an editable name. Stored as an optional `name` on `SessionEdit` (the v2
decoder already tolerates absent keys, so no schema bump) and changed through a new
`EditOperation.rename`, so it travels the same path as every other edit and is undoable.
Defaults to a readable form of the recording's date.

## Captions sidecar

`SubtitleFile` renders `[ProjectedCue] -> String` for SRT and WebVTT, pure and tested. Times are
**composition** times, because the exported video is the edited timeline: a cue that was cut is
absent, and a cue a cut split in two becomes two entries. Written next to the chosen export
destination.

## What shipped

All of the agreed scope landed. Deviations and decisions worth recording:

**A scrub bar had to be reinstated.** Restructuring around the design's transport row
(previous / play / next) quietly dropped the only way to navigate coarsely while watching. The
old `TimelineRulerView` became `PreviewScrubBar`: a 3pt line under the picture that thickens on
hover, showing splits and markers but deliberately **not** cut boundaries — a real document has
40-odd of those and over a few hundred points they read as a grey smear. Cuts belong to the
lanes, where there is room.

**Camera styling nearly became unreachable.** `CameraStyleMenu` lost its host when the old
transport row went. It is now a section inside the layout menu, separated by a divider, because
the two are easy to confuse but fundamentally different: layout modes are keyframed and apply
from the playhead, while shape/border/shadow are properties of the whole recording.

**Palette ranking is tiered, not a flat subsequence score.** Testing found "srt" returning
"Shorten clip" (s·h·o·**r**·**t**) ahead of "Generate captions", whose keywords literally
contain "srt". Exact and prefix matches now dominate scattered subsequences; position only
breaks ties within a tier.

**`Clean audio` is the only unavailable action, and the palette omits it.** The card is shown
disabled with the reason, because the navigation is where a user learns what the app can do. The
palette excludes it — a palette is for doing things, and offering something that cannot run is
noise. A test asserts exactly this split so the two surfaces cannot drift.

**Delete and Shift+Delete are the same ripple delete**, and `B` arms the blade rather than
cutting immediately. Both are consequences of the document model rather than shortcuts: the
timeline is derived from cuts and cannot contain a gap, so "lift" is not expressible, and a bare
key that silently cut the timeline would be a trap.

**`AURA_OPEN_SESSION`** opens a session's window at launch. The studio is most of the app's
surface, and iterating on it otherwise means recording a session by hand every time. It does
nothing when unset.

**Filmstrip frames are placed by source time, not laid end to end.** Each slot asks the strip
for whichever frame covers its own moment, so zooming changes how much of the recording a
thumbnail represents instead of scrolling a fixed ribbon out of alignment with the cuts above
it.

**Cuts, splits, selection, markers and the playhead are one overlay spanning all five lanes**,
not per-lane copies. Five copies would be five chances to disagree about where a cut is, and the
design's premise is that everything stays in sync.

### Playhead following, revisited

Phase 4 deliberately stopped the timeline following the playhead, and that turned out to be the
wrong call in use: the playhead simply left the visible window during playback and there was no
way to tell where it had got to.

The reason it was switched off is still real, though — the timeline's axis is the *recording*,
so the playhead teleports across every cut, over a hundred times per playthrough on this
document. Following each jump pans the view continuously and re-reads the waveform at display
resolution every time.

So the policy is **paging**, not tracking: the window moves only when the playhead actually
leaves it, and then places it one lead-in (12%) from the leading edge, buying nearly a full
window of lookahead. A cut jump that lands inside the visible window costs nothing at all. The
decision lives in `PlayheadFollower`, a pure function, and a test walks 12,000 playback ticks
across a 400s recording to confirm it moves the window 15–25 times rather than once per tick.

Three refinements the behaviour needs to not be irritating in the other direction:

- **Only while playing.** When paused the user is inspecting something, and moving the view out
  from under them is what made following annoying in the first place.
- **But always on an explicit seek.** Clicking a transcript line or jumping to a marker that is
  off-screen should bring the timeline along, or the playhead lands somewhere invisible.
- **Suspended during a timeline drag.** Otherwise dragging a selection while audio plays can
  page the view out from under the cursor, and the rest of the gesture runs against coordinates
  that have moved.

It is a toggle in the timeline toolbar, defaulting to on, persisted in `ReviewPreferences`. The
stored bool is inverted, because `UserDefaults` returns false for an absent key and a first
launch would otherwise read as "off".

### Panning the timeline

Two ways, both hidden until wanted.

**An overlay scrollbar**, revealed while the pointer is anywhere over the lanes and absent
entirely when the whole recording already fits — there is then nothing to scroll, and a
full-width thumb is only something to try to drag. It is overlaid at the bottom of the lane
stack rather than given its own row, in the manner of the system's overlay scrollers, so it
costs no lane height. While hidden it is also removed from the hit path, or an invisible thumb
would swallow clicks meant for the waveform underneath.

`ScrollBarGeometry` is pure and tested in both directions, because the arithmetic is where this
goes wrong: the thumb has a minimum width (32pt — at 0.5s visible out of 400s the proportional
thumb would be sub-pixel), so its travel is shorter than the track. If the two directions
disagree about that, the thumb drifts away from the cursor mid-drag. A round-trip test pins it
across four zoom levels.

**Two-finger horizontal scrolling**, through an `NSEvent` scroll monitor rather than a view in
the hierarchy. A view can only receive `scrollWheel` if it is hit-testable, and a hit-testable
overlay across the lanes would swallow the clicks and drags the timeline depends on — the same
reason the keyboard is a monitor. It requires the horizontal component to dominate, so a
slightly-off vertical gesture cannot nudge the view sideways, and it scales legacy line-based
wheel deltas so a mouse feels like the trackpad. An unhandled scroll falls through rather than
being eaten.

Both suspend playhead following for the duration of the interaction, so the view cannot page
while being dragged.

### Verified against the real recording

Launched against the user's session (421.68s, 127 cuts):

- Both filmstrip caches extracted and written — 211 frames each at a 2s interval covering 422s,
  every JPEG valid, index byte-exact, 824KB (screen, 160×90) and 1.0MB (camera, 120×90).
- `edit.json` migrated v1 → v2 with a `.v1.bak` backup preserved.
- `transcriptIdentity` stamped as `w631-2fbb6fa05b134290`, which is the regression check for the
  Phase 4 bug where the stamp was discarded whenever the word-cut spans were already correct.
- No crash, clean log, no build warnings, 511 unit tests passing.

Not verified: the appearance itself. `screencapture` is unavailable in this environment, so the
layout, the dark palette, the subtitle placement and the filmstrip rendering need a human look.

## Verification

1. `./scripts/test.sh` — all unit tests pass.
2. The window opens dark, with traffic lights over the custom header and no system titlebar.
3. The preview holds the majority of the height at 900pt and at full screen; the timeline stays
   between 220 and 420pt.
4. Subtitles sit inside the picture at both a wide and a tall window aspect — the regression
   check for fitting against the video rect rather than the container.
5. Screen and Camera lanes show frames; scrubbing and zooming re-slice without flicker; deleting
   the cache re-extracts.
6. A cut shades identically across all five lanes, and the caption block for a cut cue reads as
   removed.
7. "Remove silences" produces one undoable operation that reverses completely with one Cmd+Z.
8. Cmd+K opens the palette, typing filters, Enter runs, and Escape closes without applying.
9. Space still types a space into the AI prompt, and Cmd+Z there still undoes typing — the
   Phase 4 regressions stay fixed.
10. Export writes both the video and a sidecar `.srt` whose timings match the edited timeline.
