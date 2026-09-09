# LLD: Aura Phase 1 — Recording Core

Jira: KAN-28 (epic KAN-27). This covers Phase 1 of Milestone 1 only — the recording core.
Phase 2 (push-to-talk voice control, whisper.cpp, TTS confirmations) is a separate, later LLD.

## Scope

- Menu-bar app (`MenuBarExtra`) with a manual screen/window/app picker and Start/Pause/Resume/Stop
  controls — voice control doesn't exist yet, so this UI is the only way to drive recording.
- Simultaneous 4-track capture into a session folder: `screen.mov`, `camera.mov`,
  `microphone.m4a`, `system-audio.m4a`, plus an append-only `events.jsonl`.
- Pause/resume that rebases timestamps to skip paused wall-clock time entirely, without ever
  stopping the underlying capture sessions (so a future agent layer can keep sampling while
  presentation recording is paused).

## Architecture

One `AVAssetWriter`/`AVAssetWriterInput` pair per output file (`TrackWriter`), fed by:

- A single `SCStream` (`ScreenCaptureSession`) producing both `.screen` and `.audio` sample
  buffers — one stream, not two, to avoid doubling capture cost / desync risk.
- A dedicated video-only `AVCaptureSession` (`CameraRecorder`) for the webcam.
- A dedicated audio-only `AVCaptureSession` (`MicrophoneRecorder`) for the mic.

All four tracks share one `sessionStartTime` (`CMClockGetTime(CMClockGetHostTimeClock())`)
captured once at Start and passed to every `TrackWriter.start()`, which calls
`startSession(atSourceTime:)` immediately — this is what keeps the four independent files
aligned to the same wall-clock zero point.

`SCStream.startCapture()/stopCapture()` and `AVCaptureSession.startRunning()/stopRunning()` fire
exactly once each, at record Start/Stop. Pause/Resume never touches capture lifecycle — they only
flip a `PauseClock` that `TrackWriter.append` consults per sample: while paused, samples are
dropped; after resume, samples are rebased backward by the accumulated paused duration via
`CMSampleBufferCreateCopyWithNewTiming`.

`RecordingController` (`@MainActor`, `ObservableObject`) is the single orchestrator: owns all
capture objects and writers, drives `RecordingStateMachine` (pure, unit-tested), and surfaces
failures via `RecordingError`.

## Known limitations / follow-ups

- No manual VideoToolbox — `AVAssetWriterInput` hardware-encodes H.264/HEVC directly from
  appended sample buffers, which is sufficient for Phase 1 (no custom compositing needed).
- Screen Recording permission has no Info.plist key or pre-flight API; denial surfaces as
  `SCShareableContent`/`SCStream` throwing. After granting it in System Settings, an
  already-running instance of the app must be relaunched before capture will actually start.
- Dock icon is intentionally left visible for now (easier to spot/quit during development);
  flip to `LSUIElement = YES` once the app is stable.
- `Voice/` and `Agent/` source directories exist as empty placeholders for Phase 2+.

See `/Users/vslala/.claude/plans/bright-snacking-pizza.md` for the full approved plan this was
built from, including the manual verification steps.
