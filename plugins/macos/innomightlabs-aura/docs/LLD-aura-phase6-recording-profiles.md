# Aura Phase 6 — Recording Profiles

## Context

Phases 1–5 built one recording shape: screen, camera, microphone and system audio, always, on
four separate tracks. That was the right thing to build first — four independent tracks is the
hard part, and every editing feature since depends on it. But it is also the *only* thing Aura
can record, which makes it wrong for most of what people actually record:

- A podcast is microphone only. Aura currently opens the camera, holds a `SCStream` on a
  display nobody is looking at, and writes two video files that will never be used.
- A screen demo with system audio and no narration still demands camera permission and records
  a face nobody asked for.
- A talking-head clip is camera only, and should fill the frame at the camera's native
  resolution rather than sit in a corner over a black screen.

This phase makes **what gets recorded** a user choice, and makes the studio honest about
whatever came back.

### What is already true (and therefore not in this phase)

The review layer is, by design, indifferent to missing tracks. This was established in Phase 3
and it holds:

- `SourceTrackProbe.probe` returns `nil` for a file that is absent, empty or truncated, so
  every track is already optional as far as the editor is concerned
  (`Review/Composition/SourceTrackProbe.swift`).
- `TimelineResolver.resolve` already picks `byKind[.screen] ?? byKind[.camera]` as the base
  layer, so a camera-only session already composites the camera full-frame at its own render
  size (`Review/Composition/TimelineResolver.swift:28`).
- `LayerInstructionCompositionBuilder` already builds an audio-only composition: it only throws
  `CompositionError.noUsableMedia` when base, overlay *and* audio are all absent
  (`LayerInstructionCompositionBuilder.swift:37`).
- `TimelineView.lanes` already filters lanes by which tracks exist, so empty Screen/Camera rows
  never appear (`Review/Timeline/TimelineView.swift:32`).
- `SessionDigest.make` derives its track list from the probes, so the agent is already told the
  truth about an audio-only session (`Agent/SessionDigest.swift:198`).
- Every `StudioAction` — silences, fillers, captions, highlights, shorten — is transcript and
  waveform driven, so all of them work on a podcast unchanged.

The hard-wired part is the **recording** side, and there are exactly three places:

| Where | What it assumes |
| --- | --- |
| `RecordingController.start` (`Recording/RecordingController.swift:58`) | Builds all four `TrackWriter`s unconditionally, starts all three capture sources unconditionally. |
| `RecordingController.checkDevicePermissions` (`:313`) | Demands camera **and** microphone authorization, even for a screen-only capture. |
| `ScreenCaptureSession.start` (`Recording/ScreenCaptureSession.swift:18`) | Always adds both the `.screen` and `.audio` stream outputs, always `capturesAudio = true`. |

Plus two places in the studio that are dishonest when a track is missing rather than broken:
the preview stage renders a black rectangle for an audio-only session, and Export always writes
`.mp4`.

### Scope, as agreed

**In:** a `RecordingProfile` model with named presets and per-source toggles; a `CaptureSource`
strategy per recorded device, so the recorder composes a source list instead of branching on
what is enabled; audio-only `SCStream` for system audio without screen video; a microphone
device picker with a pre-roll level meter; a session manifest recording what was asked for; a
waveform-dominant studio stage for sessions with no video; audio-only export as `.m4a` plus the
existing subtitle sidecar; camera resolution chosen by role.

**Out, deliberately:** burned-in captions (Phase 5's reasoning stands — they cannot be turned
off later, and sidecar `.srt`/`.vtt` already exists); audiogram video render for podcasts (a
frame-generator project, and it only makes sense once caption styling settles); input
monitoring to headphones (see [Deferred](#deferred)); multi-microphone and per-guest tracks;
side-by-side layout.

### The design decision that shapes this phase

The obvious implementation — thread the profile into `RecordingController` and guard each step
with `if profile.camera` — spreads one decision across five unrelated concerns: permission
requests, writer construction, callback wiring, source start, and teardown. Five sites asking
the same question is how the fifth ends up disagreeing with the other four, and it is a
conditional per source *per concern*, so adding a fifth source later means five more branches.

Instead: **each recordable device becomes a `CaptureSource` strategy that owns its own device
session, its own writers and its own callback wiring**, and `RecordingController` holds
`[any CaptureSource]` and fans the lifecycle over the list. Source selection happens once, in a
factory.

| Concern | Conditional design | Strategy design |
| --- | --- | --- |
| Permissions | `if` per device in `checkDevicePermissions` | `for source in sources { try await source.prepare() }` |
| Writers | `switch` over four kinds | each source creates its own from its own track specs |
| Callback wiring | three guarded blocks | each source wires itself in `start` |
| Start / rollback / stop / teardown | `if` × 3 in each of four methods | `sources.forEach { … }` |
| Mute | an `isMicMuted` flag read on the audio queue | `setMuted` on the protocol, default no-op |
| Screenshot | a pixel buffer cached by the screen callback | `latestVideoFrame` on the protocol, default nil |
| **Selection** | — | one factory, ~12 lines |

This is not a speculative abstraction. Three parallel implementations with near-identical
lifecycles already exist (`ScreenCaptureSession`, `CameraRecorder`, `MicrophoneRecorder`) with
no common type, and one-method protocol seams are already this codebase's idiom
(`CompositionBuilding`, `ExportEngine`, `EditSuggesting`). The protocol describes what is
already there.

Two conditionals genuinely remain, and both are platform shape rather than design:

1. **`SCStream` produces screen video and system audio from one session.** They are not
   independent devices, so `ScreenCaptureSource` takes a `Set<TrackKind>` and has two internal
   `if`s deciding which stream outputs to attach. Modelling them as two sources would mean a
   shared-stream resource with reference counting — more machinery to express less truth.
2. **The camera must be configured before its writer's output settings are known**, because
   `activeFormat` is only accurate after the session preset applies (§2.3). That is an ordering
   constraint on the protocol — `prepare()` then `start(context:)` — not a branch.

---

## 1. The model

New file, `Sources/Aura/Recording/RecordingProfile.swift`.

Because sources are now a list, the profile is a **set of track kinds** rather than four
booleans. `TrackKind` already exists and already enumerates exactly the four sources
(`Review/Composition/SourceTrackProbe.swift:5`), and its raw values are already the strings
written into `events.jsonl` — so the profile reuses it rather than introducing a parallel
vocabulary. It gains `Codable` (free, `String`-backed) and the two display properties the
toggle rows need.

```swift
/// Which sources a recording captures.
///
/// A set, not four flags: the recorder builds one `CaptureSource` per enabled kind and fans the
/// lifecycle over the list, and the picker renders one row per `TrackKind.allCases`. Both are
/// collection operations, and neither has a branch per source.
struct RecordingProfile: Equatable, Codable, Sendable {
    var tracks: Set<TrackKind>

    static let fullStudio = RecordingProfile(tracks: Set(TrackKind.allCases))

    /// Nothing selected is not a recording. The Start button is disabled on this, and
    /// `RecordingController.start` guards on it too — a disabled button is a UI state, not an
    /// invariant.
    var isRecordable: Bool { !tracks.isEmpty }

    /// Always derived through `allCases`, never by iterating the set: a `Set` has no order, and
    /// writer creation, teardown and the `track_start` events must be deterministic.
    var enabledKinds: [TrackKind] { TrackKind.allCases.filter(tracks.contains) }

    var hasVideo: Bool { enabledKinds.contains(where: \.isVideo) }
    var isAudioOnly: Bool { isRecordable && !hasVideo }

    /// The kinds `SCStream` is responsible for. Non-empty means one `ScreenCaptureSource`.
    var screenCaptureKinds: Set<TrackKind> {
        tracks.intersection(ScreenCaptureSource.supportedKinds)
    }

    /// System audio is captured *through* ScreenCaptureKit, so it needs the same TCC grant and
    /// the same stream as screen video — which is why an audio-only podcast that wants a remote
    /// guest still triggers the Screen Recording prompt.
    var needsScreenCaptureStream: Bool { !screenCaptureKinds.isEmpty }

    mutating func set(_ kind: TrackKind, enabled: Bool) {
        if enabled { tracks.insert(kind) } else { tracks.remove(kind) }
    }
}
```

`TrackKind` additions, alongside its existing `mediaType` / `isVideo` / `lane` / `videoLane`:

```swift
extension TrackKind {
    /// The user's word for this source. "Voice" rather than "Microphone", matching
    /// `TimelineLane.title` — the picker and the timeline must not name the same track
    /// differently.
    var title: String {
        switch self {
        case .screen: return "Screen"
        case .camera: return "Camera"
        case .microphone: return "Voice"
        case .systemAudio: return "System Audio"
        }
    }

    var symbol: String {
        switch self {
        case .screen: return "display"
        case .camera: return "camera"
        case .microphone: return "mic"
        case .systemAudio: return "speaker.wave.2"
        }
    }
}
```

These duplicate `TimelineLane.title`/`symbol` for the three lanes that overlap. That is
deliberate and cheap: `TimelineLane` includes `captions`, which is not a recordable source, and
`TrackKind` includes nothing else — coupling them would mean one enum serving two different
domains. The duplication is four strings; the test table below pins them equal so they cannot
drift.

### Presets

```swift
/// The named modes in the menu bar. A preset is a shortcut that *writes* a profile; the
/// profile remains the source of truth, and a profile matching no preset is "Custom".
enum RecordingPreset: String, CaseIterable, Identifiable, Sendable {
    case fullStudio
    case screenAndVoice
    case screenAndSystemAudio
    case podcast
    case cameraOnly

    var id: String { rawValue }

    var title: String {
        switch self {
        case .fullStudio: return "Full Studio"
        case .screenAndVoice: return "Screen + Voice"
        case .screenAndSystemAudio: return "Screen + System Audio"
        case .podcast: return "Podcast (audio only)"
        case .cameraOnly: return "Camera only"
        }
    }

    var profile: RecordingProfile {
        switch self {
        case .fullStudio:
            return .fullStudio
        case .screenAndVoice:
            return RecordingProfile(tracks: [.screen, .microphone])
        case .screenAndSystemAudio:
            return RecordingProfile(tracks: [.screen, .systemAudio])
        // Voice only, not voice + system audio: system audio would drag in the Screen
        // Recording permission that an audio-only recording otherwise never needs. A remote
        // guest is one visible toggle away, which makes it a choice rather than a surprise.
        case .podcast:
            return RecordingProfile(tracks: [.microphone])
        // With the mic, because a talking head with no voice is not a thing anyone records.
        case .cameraOnly:
            return RecordingProfile(tracks: [.camera, .microphone])
        }
    }

    /// The preset a profile corresponds to, or nil for Custom.
    static func matching(_ profile: RecordingProfile) -> RecordingPreset? {
        allCases.first { $0.profile == profile }
    }
}
```

### The request

`RecordingController.start` already takes `(target:cameraDeviceID:)` and would now need a
profile and a microphone id as well. Four positional arguments that must agree with each other
is exactly the shape that grows a fifth, so they become one value with the agreement expressed
as `isValid`. New file, `Sources/Aura/Recording/RecordingRequest.swift`:

```swift
/// What the user asked to record, with the profile/target agreement checked in one pure place.
/// The factory in §2.4 turns this into capture sources; nothing downstream reads it.
struct RecordingRequest: Sendable {
    var profile: RecordingProfile
    /// The `SCStream` content filter source. Required whenever the profile needs a stream —
    /// including system-audio-without-screen, where ScreenCaptureKit still requires a filter
    /// even though no `.screen` output is attached. The picker supplies the primary display in
    /// that case, so neither the factory nor the source has a special case.
    var screenTarget: CaptureTarget?
    var cameraDeviceID: String?
    var microphoneDeviceID: String?

    var isValid: Bool {
        guard profile.isRecordable else { return false }
        if profile.needsScreenCaptureStream && screenTarget == nil { return false }
        return true
    }
}
```

`RecordingError` gains one case:

```swift
case noSourcesSelected
// "Pick at least one thing to record — screen, camera, microphone or system audio."
```

---

## 2. The capture source strategy

### 2.1 The protocol

New file, `Sources/Aura/Recording/CaptureSource.swift`.

```swift
/// What every capture source is handed at start: the session it writes into, and the one shared
/// host time its writers must be anchored to.
///
/// The start time is passed in rather than read per source, because a single shared origin is
/// exactly what keeps the tracks mutually aligned — `SourceTrackProbe.alignmentCorrection` and
/// the `track_start` offsets are both measured against it. A source reading its own clock would
/// reintroduce the desync those exist to remove.
struct CaptureContext: Sendable {
    let folder: SessionFolder
    let sessionStartTime: CMTime
}

/// One recordable device, owning its device session, its `TrackWriter`s and its own callback
/// wiring.
///
/// `RecordingController` composes a list of these from the profile and fans the lifecycle over
/// it, so adding or removing a recordable source is one conformer and one line in
/// `CaptureSourceFactory` — not a branch in five methods.
///
/// Classes, and `@unchecked Sendable` like the three implementations already are: each owns a
/// capture queue that appends to its writers, while `start`/`stop` are driven from the main
/// actor.
protocol CaptureSource: AnyObject, Sendable {
    /// The tracks this source writes. Known before `start`, so the controller can report
    /// per-track without asking what any given source is.
    var kinds: [TrackKind] { get }

    /// The writers this source created, available after `start`. Owned here; the controller
    /// only fans the shared pause/resume/finish over them, because those three must happen at
    /// one host time across every track at once.
    var writers: [TrackKind: TrackWriter] { get }

    /// Reported when the source dies mid-recording. Only `ScreenCaptureSource` currently can.
    var onFailure: (@Sendable (Error) -> Void)? { get set }

    /// Permission prompts and device configuration, before any file exists. Throws
    /// `RecordingError` so the menu bar can explain what was refused.
    func prepare() async throws

    /// Creates and starts this source's writers, wires its callbacks, starts its device
    /// session. Throwing here is a failed start; the controller cancels every source.
    func start(context: CaptureContext) throws

    func stop() async
    func cancel()

    /// Muting is a property of sources that can be muted. A default no-op is what lets the
    /// controller say `sources.forEach { $0.setMuted(true) }` without asking which is the mic.
    func setMuted(_ muted: Bool)

    /// The most recent full frame, for `screenshot()`. Default nil.
    var latestVideoFrame: CVPixelBuffer? { get }
}

extension CaptureSource {
    func setMuted(_ muted: Bool) {}
    var latestVideoFrame: CVPixelBuffer? { nil }
}
```

Two helpers every conformer needs, so writer construction is written once rather than three
times. Also in `CaptureSource.swift`:

```swift
/// Everything needed to create one `TrackWriter`, as a value — so a source declares its tracks
/// and a single shared function builds them.
struct TrackSpec {
    let kind: TrackKind
    let outputURL: URL
    let outputFileType: AVFileType
    let outputSettings: [String: Any]

    static func video(kind: TrackKind, url: URL, pixelSize: CGSize) -> TrackSpec { … }
    static func audio(kind: TrackKind, url: URL) -> TrackSpec { … }
}

extension CaptureSource {
    /// Builds and starts a writer per spec. One implementation, so a new source cannot get the
    /// `startSession(atSourceTime:)` anchoring subtly wrong.
    func makeWriters(_ specs: [TrackSpec], context: CaptureContext) throws -> [TrackKind: TrackWriter] {
        var writers: [TrackKind: TrackWriter] = [:]
        for spec in specs {
            let writer = try TrackWriter(
                outputURL: spec.outputURL,
                outputFileType: spec.outputFileType,
                mediaType: spec.kind.mediaType,
                outputSettings: spec.outputSettings,
                sessionStartTime: context.sessionStartTime
            )
            try writer.start()
            writers[spec.kind] = writer
        }
        return writers
    }
}
```

The two output-settings builders move verbatim out of `RecordingController`
(`videoOutputSettings(pixelSize:)`, `audioOutputSettings()`) into `TrackSpec`'s factories.
`SystemAudioSink` (`Audio/SystemAudioSink.swift`) is deleted: it exists only to adapt the
stream's audio callback to a writer, which `ScreenCaptureSource` now does inline.

### 2.2 `ScreenCaptureSource`

`Sources/Aura/Recording/ScreenCaptureSource.swift` — today's `ScreenCaptureSession` with writer
ownership folded in, and the two stream outputs driven by the requested kinds.

```swift
/// Screen video and/or system audio: one `SCStream`, one or two tracks.
///
/// The only source that writes more than one track, because ScreenCaptureKit genuinely produces
/// both from a single stream. Splitting it into two sources would mean sharing one stream
/// between them with reference-counted start/stop — more machinery to express less truth.
final class ScreenCaptureSource: NSObject, CaptureSource, @unchecked Sendable {
    static let supportedKinds: Set<TrackKind> = [.screen, .systemAudio]

    private let target: CaptureTarget
    private let requested: Set<TrackKind>

    var kinds: [TrackKind] { TrackKind.allCases.filter(requested.contains) }
    private(set) var writers: [TrackKind: TrackWriter] = [:]
    var onFailure: (@Sendable (Error) -> Void)?

    /// Last-write-wins cache of the most recent complete frame, for `screenshot()`. Written on
    /// the video queue, read on the main actor — `CVPixelBuffer` retain/release is thread-safe,
    /// so no lock is needed.
    private(set) var latestVideoFrame: CVPixelBuffer?

    private var capturesVideo: Bool { requested.contains(.screen) }
    private var capturesAudio: Bool { requested.contains(.systemAudio) }

    init(target: CaptureTarget, kinds: Set<TrackKind>) {
        self.target = target
        self.requested = kinds.intersection(Self.supportedKinds)
    }

    /// Screen Recording has no pre-flight authorization API: a denied or not-yet-granted state
    /// surfaces as `SCShareableContent.current` throwing in the picker, or `startCapture()`
    /// throwing in `start`. So there is nothing to do here.
    func prepare() async throws {}

    func start(context: CaptureContext) throws {
        var specs: [TrackSpec] = []
        if capturesVideo {
            specs.append(.video(kind: .screen, url: context.folder.screenURL, pixelSize: target.pixelSize))
        }
        if capturesAudio {
            specs.append(.audio(kind: .systemAudio, url: context.folder.systemAudioURL))
        }
        writers = try makeWriters(specs, context: context)
        try startStream()
    }
    …
}
```

The stream configuration is the one substantive behaviour change:

```swift
private func startStream() throws {
    let configuration = SCStreamConfiguration()
    configuration.queueDepth = 5
    configuration.pixelFormat = kCVPixelFormatType_32BGRA
    configuration.showsCursor = true
    configuration.capturesAudio = capturesAudio
    configuration.excludesCurrentProcessAudio = true

    if capturesVideo {
        let pixelSize = target.pixelSize
        configuration.width = Int(pixelSize.width)
        configuration.height = Int(pixelSize.height)
        configuration.minimumFrameInterval = CMTime(value: 1, timescale: 30)
    } else {
        // ScreenCaptureKit has no audio-only stream: a filter and a configuration are always
        // required. No `.screen` output is attached below, so no frame is ever delivered — but
        // a display-sized configuration would still have the stream allocate a buffer pool for
        // pixels nobody reads. 2x2 at 1fps is the cheapest legal configuration.
        configuration.width = 2
        configuration.height = 2
        configuration.minimumFrameInterval = CMTime(value: 1, timescale: 1)
    }

    let stream = SCStream(filter: target.contentFilter(), configuration: configuration, delegate: self)
    if capturesVideo { try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: videoQueue) }
    if capturesAudio { try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: audioQueue) }
    Task { try await stream.startCapture() }
    self.stream = stream
}
```

The `SCStreamOutput` callback keeps today's `isCompleteFrame` filter verbatim — appending a
non-`.complete` frame corrupts the encoder pipeline, and that comment is load-bearing — and now
appends straight to `writers[.screen]` / `writers[.systemAudio]` instead of calling out through
closures. `SCStreamDelegate.stream(_:didStopWithError:)` forwards to `onFailure`.

**Needs device verification.** Attaching only the `.audio` output is the approach Apple's own
screen-capture sample uses for audio-only capture, but it is not documented as a supported
configuration, and `startCapture()` is the kind of API that can reject it. Step 4 of the
implementation order verifies it on hardware before anything depends on it; the fallback if it
is rejected is to attach the `.screen` output at 2x2/1fps and drop every buffer in the handler,
which costs one wasted decode per second and is contained entirely inside this file.

### 2.3 `CameraCaptureSource` and `MicrophoneCaptureSource`

`Sources/Aura/Recording/CameraCaptureSource.swift` and
`Sources/Aura/Recording/MicrophoneCaptureSource.swift` — today's `CameraRecorder` and
`MicrophoneRecorder`, conformed, with their `AVCaptureSession` setup unchanged.

Both implement `prepare()` as authorization plus device configuration, which is where the
scoped-permission behaviour now lives — there is no `checkDevicePermissions` any more, and no
profile to consult, because a source that exists is a source that was asked for:

```swift
/// Shared by the two `AVCaptureDevice`-backed sources.
enum CaptureAuthorization {
    static func request(_ media: AVMediaType, denied: RecordingError) async throws {
        switch AVCaptureDevice.authorizationStatus(for: media) {
        case .authorized:
            return
        case .notDetermined:
            guard await AVCaptureDevice.requestAccess(for: media) else { throw denied }
        default:
            throw denied
        }
    }
}
```

`CameraCaptureSource.prepare()` calls it with `(.video, denied: .cameraPermissionDenied)` and
then configures the session, caching the pixel size its writer needs. This fixes an existing
defect: `CameraRecorder.devicePixelSize(deviceID:)` reads `activeFormat` *before* the session
preset applies, so the declared size can disagree with what actually gets encoded — which is
precisely the disagreement `SourceTrackProbe` documents having to work around.

```swift
/// How much camera resolution this recording justifies. Passed in by the factory, because only
/// the profile knows whether the camera is the frame or a corner of it.
enum CameraQuality: Sendable {
    /// The camera is the whole frame (no screen track).
    case primary
    /// The camera is a corner overlay, typically a quarter of the frame's width.
    case overlay

    var preset: AVCaptureSession.Preset {
        switch self {
        case .primary: return .hd1920x1080
        case .overlay: return .hd1280x720
        }
    }
}

func prepare() async throws {
    try await CaptureAuthorization.request(.video, denied: .cameraPermissionDenied)

    guard let device = Self.resolveDevice(deviceID: deviceID) else {
        throw RecordingError.writerSetupFailed("No camera device found")
    }
    let input = try AVCaptureDeviceInput(device: device)

    session.beginConfiguration()
    if session.canSetSessionPreset(quality.preset) { session.sessionPreset = quality.preset }
    if session.canAddInput(input) { session.addInput(input) }
    output.setSampleBufferDelegate(self, queue: queue)
    if session.canAddOutput(output) { session.addOutput(output) }
    session.commitConfiguration()

    // Read *after* the preset applied, which is the whole reason configuration lives in
    // `prepare` and not in `start`.
    let dimensions = CMVideoFormatDescriptionGetDimensions(device.activeFormat.formatDescription)
    pixelSize = CGSize(width: CGFloat(dimensions.width), height: CGFloat(dimensions.height))
}

func start(context: CaptureContext) throws {
    writers = try makeWriters(
        [.video(kind: .camera, url: context.folder.cameraURL, pixelSize: pixelSize ?? Self.fallbackPixelSize)],
        context: context
    )
    session.startRunning()
}
```

`MicrophoneCaptureSource` is the same shape with `(.audio, denied: .microphonePermissionDenied)`,
a `.audio(kind: .microphone, url:)` spec, and device resolution by `uniqueID` — the capability
`MicrophoneRecorder` lacks today:

```swift
static func availableDevices() -> [AVCaptureDevice] {
    AVCaptureDevice.DiscoverySession(
        deviceTypes: [.microphone, .external],
        mediaType: .audio,
        position: .unspecified
    ).devices
}
```

It is also the one source that implements `setMuted`, replacing the controller's `isMicMuted`
flag:

```swift
/// Written on the main actor, read on the capture queue. A stale read for one buffer is
/// harmless — worst case one extra or missing sample at the mute boundary — unlike
/// `PauseClock`, where exact correctness is required.
private var isMuted = false

func setMuted(_ muted: Bool) { isMuted = muted }

// In the sample buffer delegate:
guard !isMuted else { return }
writers[.microphone]?.append(sampleBuffer)
```

`devicePixelSize(deviceID:)` is deleted; its only caller was
`RecordingController.start:76`.

### 2.4 The factory

New file, `Sources/Aura/Recording/CaptureSourceFactory.swift`. This is the one place source
selection happens, and it is pure apart from constructing the sources.

```swift
/// Turns a request into the sources that will record it.
///
/// The single site where "is this source enabled" is asked. Everything downstream iterates the
/// returned list, which is why the recorder has no per-source branches.
enum CaptureSourceFactory {
    static func sources(for request: RecordingRequest) -> [any CaptureSource] {
        var sources: [any CaptureSource] = []

        // One source for both, because one `SCStream` produces both. See §2.2.
        let screenKinds = request.profile.screenCaptureKinds
        if !screenKinds.isEmpty, let target = request.screenTarget {
            sources.append(ScreenCaptureSource(target: target, kinds: screenKinds))
        }
        if request.profile.tracks.contains(.camera) {
            sources.append(CameraCaptureSource(
                deviceID: request.cameraDeviceID,
                // The camera is the frame unless a screen track will be under it.
                quality: request.profile.tracks.contains(.screen) ? .overlay : .primary
            ))
        }
        if request.profile.tracks.contains(.microphone) {
            sources.append(MicrophoneCaptureSource(deviceID: request.microphoneDeviceID))
        }

        return sources
    }
}
```

Testable without any device: `sources(for:)` returns the right *count and kinds* for every
preset, which is the property that matters and the one a conditional recorder cannot assert at
all.

### 2.5 `RecordingController` becomes a lifecycle fan-out

The controller keeps everything that must be shared across tracks — the state machine, the
session start time, the pause clock mirror, event logging — and loses everything per-source.
Its three concrete source properties, its four writer properties, `wireCallbacks`,
`checkDevicePermissions`, `isMicMuted`, `latestVideoPixelBuffer`, `systemAudioSink`,
`writersByKind` and the two output-settings builders all go.

```swift
private var sources: [any CaptureSource] = []

/// Ordered by `TrackKind.allCases`, so events and teardown are deterministic regardless of
/// source order.
private var writersByKind: [(TrackKind, TrackWriter)] {
    let all = sources.reduce(into: [TrackKind: TrackWriter]()) { $0.merge($1.writers) { a, _ in a } }
    return TrackKind.allCases.compactMap { kind in all[kind].map { (kind, $0) } }
}

private var allTrackWriters: [TrackWriter] { writersByKind.map(\.1) }

func start(_ request: RecordingRequest) async {
    guard request.isValid else {
        lastError = request.profile.isRecordable
            ? .writerSetupFailed("Choose a display or window to record.")
            : .noSourcesSelected
        return
    }
    guard applyTransition(.start) else { return }

    let sources = CaptureSourceFactory.sources(for: request)

    do {
        // Permission prompts and device configuration, before a session directory exists —
        // so a refusal leaves nothing behind.
        for source in sources {
            try await source.prepare()
        }

        let manager = SessionManager()
        try manager.createSessionDirectory()

        let startTime = CMClockGetTime(CMClockGetHostTimeClock())
        let context = CaptureContext(folder: manager.folder, sessionStartTime: startTime)

        self.sessionManager = manager
        self.sessionStartTime = startTime
        self.sources = sources

        // `let` is enough: `CaptureSource` is `AnyObject`-constrained, so a property can be set
        // through the existential without a mutable binding.
        for source in sources {
            source.onFailure = { [weak self] error in
                Task { @MainActor [weak self] in self?.handleSourceFailure(error) }
            }
            try source.start(context: context)
        }

        try manager.writeManifest(RecordingManifest(request: request, startedAt: Date()))

        currentProfile = request.profile
        currentTargetName = request.profile.tracks.contains(.screen) ? request.screenTarget?.displayName : nil
        logEvent(.recordStart, at: startTime, app: currentTargetName, label: request.profile.eventLabel)
        applyTransition(.didStart)
    } catch let error as RecordingError {
        await rollbackFailedStart()
        lastError = error
    } catch {
        await rollbackFailedStart()
        lastError = .writerSetupFailed(error.localizedDescription)
    }
}
```

Every other lifecycle method becomes a fan-out with no knowledge of what is recording:

```swift
func mute()  { sources.forEach { $0.setMuted(true) } }
func unmute() { sources.forEach { $0.setMuted(false) } }

private func stopSources() async {
    for source in sources { await source.stop() }
}

func screenshot() async {
    guard state == .recording || state == .paused else { return }
    // First source with a frame, in `TrackKind.allCases` order — so screen wins when both are
    // recording, and a camera-only session gets screenshots for free.
    guard let pixelBuffer = sources.lazy.compactMap(\.latestVideoFrame).first,
          let sessionManager
    else { return }
    …
}

private func tearDownSessionState() {
    sessionManager?.close()
    sessionManager = nil
    sources = []
    currentTargetName = nil
    currentProfile = nil
    accumulatedPausedDuration = .zero
    pauseStartedAt = nil
}
```

`pause()`, `resume()`, `stop()`, `cancel()`, `finishWriters()` and `logTrackStartOffsets()` are
**unchanged**: they already fan out over `allTrackWriters` / `writersByKind` with a single host
time, which is the invariant that keeps the tracks aligned and is exactly why pause/resume/finish
stay on the controller rather than moving onto the protocol. Only their inputs got shorter.

One subtlety to preserve: `stop()` currently stops the capture sources, *then* calls
`logTrackStartOffsets()`, *then* finishes the writers. That order is load-bearing — the offsets
are read from the writers before teardown — and the source list must therefore not be cleared
until after `finishWriters()`.

`var currentProfile: RecordingProfile?` is published so the menu bar can say
`Recording · Screen, Voice` instead of just naming the target. `RecordingProfile.eventLabel`
is `enabledKinds.map(\.rawValue).joined(separator: "+")`.

### 2.6 What each disabled source actually saves

The user-visible promise is "saving resources", so it is worth being precise about what is and
is not saved. With the strategy design this is literal: a disabled source is an object that was
never constructed.

| Source off | Saved |
| --- | --- |
| Camera | An `AVCaptureSession` with a live device input, one HEVC encode at 720p–1080p/30, one `AVAssetWriter`, the camera indicator light, and (later) filmstrip extraction on open. |
| Microphone | An `AVCaptureSession`, one AAC encode, one `AVAssetWriter`, the mic indicator, and (later) waveform peak extraction and transcription on open. |
| Screen | The full-resolution `SCStream` video path — one 32BGRA frame per 1/30s at display resolution — plus one HEVC encode at that resolution and one `AVAssetWriter`. This is the largest single saving on a Retina display. |
| System audio | The `.audio` stream output, one AAC encode, one `AVAssetWriter`, peak extraction. |
| Screen **and** system audio | The entire `SCStream` — `CaptureSourceFactory` constructs no `ScreenCaptureSource` at all — and with it the Screen Recording TCC dependency. A microphone-only podcast touches no ScreenCaptureKit API. |

Storage follows the same shape: a podcast session is one `.m4a` plus `events.jsonl`, which is
roughly two orders of magnitude smaller than a full-studio session of the same length.

---

## 3. The session manifest

New file, `Sources/Aura/Session/RecordingManifest.swift`, written to `recording.json` beside
the existing `events.jsonl` / `transcript.json` / `edit.json` / `digest.json`.

```swift
/// What the user asked to record, as distinct from what came back.
///
/// **Behaviour is never derived from this.** The editor decides what it can do from the files
/// that actually exist (`SourceTrackProbe.probeAll`), which is the only honest source: a
/// requested camera track can still come back empty if the device was unplugged mid-recording,
/// and a manifest-driven editor would then offer camera controls for a track with no frames.
/// The manifest is for *explanation* — "Camera was recording but produced no frames" instead of
/// silently promoting the camera-less composition — and for making a session folder
/// self-describing.
struct RecordingManifest: Codable, Equatable, Sendable {
    static let currentSchemaVersion = 1

    var schemaVersion: Int
    var profile: RecordingProfile
    var startedAt: Date
    /// Display names, for labels and diagnostics. Not identifiers: devices come and go, and
    /// nothing is ever resolved from these.
    var screenTargetName: String?
    var cameraName: String?
    var microphoneName: String?

    /// `.iso8601` on both sides, so `recording.json` is readable by eye and by anything else
    /// that ever looks at a session folder. There is no shared coder extension in the codebase
    /// today — `EditDocumentStore`, `EventLogWriter` and `SessionDigest` each configure their
    /// own — so this follows that pattern rather than introducing one for a second caller that
    /// may never come.
    static func load(from url: URL) -> RecordingManifest? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try? decoder.decode(RecordingManifest.self, from: data)
    }
}
```

The profile encodes as the track kinds' raw values — the same strings `events.jsonl` already
uses for `track_start` labels:

```json
{
  "schemaVersion": 1,
  "profile": { "tracks": ["microphone"] },
  "startedAt": "2026-09-14T10:04:22Z",
  "microphoneName": "Shure MV7"
}
```

`SessionFolder` gains `let manifestURL: URL` = `recording.json`, initialised alongside the
others in the private `init` (`Session/SessionFolder.swift:58`). `existingSessions` keeps
filtering on `events.jsonl` — every session has one, including pre-Phase-6 sessions, and
switching the predicate would hide the entire back catalogue.

`SessionManager` gains `func writeManifest(_ manifest: RecordingManifest) throws`, called from
`start()` after the sources are running, so a failed start leaves no manifest behind for a
session directory `rollbackFailedStart` is about to abandon.

The `record_start` event also gains a `label` carrying the compact profile string
(`"screen+microphone"`). `events.jsonl` is the append-only record of what happened, and "a
recording started, of these sources" belongs in it; it also means a session whose
`recording.json` write failed is still self-describing. `EventTimeline` needs no change — it
ignores labels on kinds it does not ask about.

---

## 4. Menu bar UI

Target layout, as agreed:

```
┌─ Aura ──────────────────────┐
│ Mode  [ Screen + Voice  ▾ ] │
│                             │
│ ▾ Sources                   │
│   [x] Screen  [Display 1 ▾] │
│   [ ] Camera  [FaceTime  ▾] │
│   [x] Voice   [MacBook   ▾] │
│        ▁▃▅█▅▃▁  -12 dB      │
│   [ ] System Audio          │
│                             │
│      [ Start Recording ]    │
└─────────────────────────────┘
```

### 4.1 One row per `TrackKind`

The four toggle rows are a `ForEach`, not four hand-written blocks — the same
conditionals-to-collection move as the recorder, one layer up. Each row is a toggle plus an
optional accessory (the source's device picker or meter), and the accessory is the only thing
that differs per kind.

New file, `Sources/Aura/App/RecordingProfileView.swift`:

```swift
ForEach(TrackKind.allCases, id: \.self) { kind in
    SourceToggleRow(kind: kind, isOn: setup.binding(for: kind)) {
        accessory(for: kind)   // picker, meter, or EmptyView
    }
}
```

New file, `Sources/Aura/App/RecordingSetupViewModel.swift`:

```swift
@MainActor
final class RecordingSetupViewModel: ObservableObject {
    /// The source of truth. A preset writes this; editing a toggle leaves the preset reading
    /// "Custom" without clearing anything.
    @Published var profile: RecordingProfile {
        didSet { RecordingPreferences.lastProfile = profile }
    }
    /// Expanded state of the Sources disclosure, persisted so a user who works in Custom is not
    /// re-collapsing it every launch.
    @Published var showsSources: Bool

    var preset: RecordingPreset? { RecordingPreset.matching(profile) }

    func apply(_ preset: RecordingPreset) { profile = preset.profile }

    /// One binding per kind, so the rows are a `ForEach` rather than four hand-written toggles.
    func binding(for kind: TrackKind) -> Binding<Bool> {
        Binding(
            get: { [weak self] in self?.profile.tracks.contains(kind) ?? false },
            set: { [weak self] in self?.profile.set(kind, enabled: $0) }
        )
    }

    init() {
        profile = RecordingPreferences.lastProfile ?? .fullStudio
        showsSources = RecordingPreferences.showsSourceToggles
    }
}
```

`RecordingPreferences` gains `lastProfile` (JSON in `UserDefaults` under
`Aura.lastRecordingProfile`, decoded tolerantly — a decode failure falls back to `.fullStudio`),
`lastMicrophoneName`, and `showsSourceToggles`. The existing `lastCaptureTargetName` /
`lastCameraName` name-matching approach is kept for devices; profiles are exact values, not
names, so they round-trip through JSON.

New file, `Sources/Aura/App/MicrophonePickerViewModel.swift`, mirroring
`CameraPickerViewModel` exactly (refresh, drop a vanished selection, restore by saved name),
backed by `MicrophoneCaptureSource.availableDevices()`.

`MenuBarContentView` keeps its current job — layout, state, recent sessions — and hands the
profile block to `RecordingProfileView`. The existing `ShareablePickerView` and camera picker
move *inside* their toggle rows rather than being separately stacked controls.

### 4.2 Behaviour

- The **Screen** row's picker is shown only when Screen is on. When Screen is off but System
  Audio is on, `ShareablePickerViewModel` still supplies a target for the stream filter:
  `selectedTarget ?? displays.first.map(CaptureTarget.display)`. That is `RecordingRequest`'s
  `screenTarget`, and it keeps the audio-only filter case out of both the factory and the source.
- **Start Recording** is disabled when `!request.isValid`, with the reason in a caption below it
  rather than a silent dead button — the same principle `StudioSection.unavailableReason`
  established: `"Pick at least one thing to record."` or `"Choose a display or window."`.
- **System Audio** on with Screen off shows a one-line note that macOS requires Screen Recording
  permission for system audio. Discovering that through a permission prompt on a podcast is the
  kind of surprise that reads as a bug.
- While recording, the status block names the live sources — `Recording · Screen, Voice` — from
  `controller.currentProfile.enabledKinds.map(\.title)`, replacing the target-name-only line.

---

## 5. Input level meter

New file, `Sources/Aura/Audio/InputLevelMonitor.swift`.

The privacy constraint is not negotiable and is already written down in this codebase:
`FeatureFlags.isWakeWordListenerEnabled` is off by default specifically so that *"Aura only
touches the microphone during a recording"* (`App/FeatureFlags.swift`). A pre-roll meter is an
exception to that, so it is a tightly scoped one:

- It runs **only** while the menu bar popover is on screen **and** the profile contains
  `.microphone`.
- It stops in `onDisappear`, on the toggle going false, and on `deinit`.
- It never writes anything anywhere.

Implementation reuses the stack already in the app — an `AVCaptureSession` with an
`AVCaptureAudioDataOutput` — rather than introducing `AVAudioEngine` for one readout. The
arithmetic is separated out so it is testable without a device — new file
`Sources/Aura/Audio/InputLevelMeter.swift`:

```swift
/// Pure. Peak/RMS in dBFS, mapped to a 0...1 bar with asymmetric smoothing: fast attack so a
/// transient is visible, slow decay so the bar is readable rather than flickering.
struct InputLevelMeter: Equatable, Sendable {
    static let floor: Double = -60

    var attack: Double = 0.5
    var decay: Double = 0.12

    func dbFS(rms: Double) -> Double { … }          // 20 * log10, floored
    func normalized(dbFS: Double) -> Double { … }   // floor...0 -> 0...1
    func smoothed(previous: Double, next: Double) -> Double { … }
}
```

During a recording the same meter is driven from `MicrophoneCaptureSource`'s existing sample
buffer callback, so the live view needs no second session — the source exposes
`var level: Double` alongside `setMuted`. A mute button with no level next to it is how people
record forty minutes of silence.

---

## 6. Studio: the audio-first stage

### 6.1 What is missing today

`ReviewWindowView.studio` always places `PreviewStageView`
(`Review/ReviewWindowView.swift:73`), which renders `VideoPreviewView` over `Color.black`. For
an audio-only session the composition genuinely has no video track, so the player shows a black
rectangle occupying the majority of the window — and the editor's most useful surface, the
waveform, is confined to a 44pt lane at the bottom.

### 6.2 The stage

New file, `Sources/Aura/Review/Preview/AudioStageView.swift`: the enabled audio lanes drawn
tall and full width, on the **same source-time window the timeline uses**
(`viewModel.visibleSpan`), so there is one zoom state and one selection model rather than two
competing ones. It is, deliberately, "the timeline's audio lanes, enlarged".

```swift
/// The stage for a recording with no video: the audio lanes at full height.
///
/// Shares `viewModel.visibleSpan` with the timeline rather than owning a second viewport —
/// zooming the timeline zooms this, and a selection made here is the same selection. What this
/// adds over the timeline lane is height: cut boundaries and speech onsets are placeable by eye
/// at 200pt in a way they are not at 44.
struct AudioStageView: View {
    @ObservedObject var viewModel: ReviewViewModel

    private var lanes: [AudioLane] {
        AudioLane.allCases.filter { lane in
            viewModel.timeline?.audio.contains { $0.lane == lane } ?? false
        }
    }
    …
}
```

`ReviewWindowView` switches on whether there is video:

```swift
if viewModel.hasVideo {
    PreviewStageView(viewModel: viewModel)
} else {
    AudioStageView(viewModel: viewModel)
}
```

with `var hasVideo: Bool { timeline?.hasVideo ?? false }` on the view model, forwarding the
`ResolvedTimeline.hasVideo` that already exists (`ResolvedTimeline.swift:134`). Two stages is a
genuine binary at a view boundary, not a strategy: they share no lifecycle and nothing iterates
them. Abstracting it would add a protocol to express one `if`.

### 6.3 Two extractions it needs

**`AudioLaneWaveform`** — `AudioLaneContent` is currently `private` inside `TimelineView.swift:393`
and is exactly the view the stage needs at a different height. It moves to
`Sources/Aura/Review/Waveform/AudioLaneWaveform.swift` unchanged apart from becoming internal.
Its detail-vs-cache logic (`usableDetail`) is subtle and must not be reimplemented.

**`SourceAxisSurface`** — cuts, splits, selection and the playhead are drawn by four private
methods in `TimelineView` (`:165`–`:258`) and the click/drag semantics by a fifth (`:268`).
The stage needs all five, and reimplementing "a click seeks, a drag over 3pt selects, a
double-click restores a cut" is how two surfaces end up disagreeing. New file
`Sources/Aura/Review/Timeline/SourceAxisSurface.swift`:

```swift
/// A surface on the recording's source-time axis: draws the shared overlays over its content
/// and owns the click/drag semantics.
///
/// Markers are deliberately not here — they are draggable, so they need the host's gesture
/// state, and only the timeline offers them.
struct SourceAxisSurface<Content: View>: View {
    @ObservedObject var viewModel: ReviewViewModel
    let window: StampSpan<Source>
    @ViewBuilder var content: (CGFloat) -> Content

    @State private var dragOrigin: Stamp<Source>?
    …
}
```

`TimelineView` then wraps its content column in it and keeps `markers(width:)` as its own
overlay. This is the only change in this phase that touches working, hard-won interaction code,
and there are no view tests — so it is a discrete step with a manual checklist (§9, step 9).

### 6.4 Controls that must stop lying

- `PreviewControlsView`'s layout menu is already gated on `viewModel.canChangeLayout`
  (`= timeline?.overlay != nil`, `ReviewViewModel.swift:211`), which is correctly false for both
  audio-only and camera-only sessions. No change.
- The fullscreen control is meaningless without video: it and the `LayoutModeMenu` hide when
  `!hasVideo`. The speed menu stays (it is useful on audio) and so does the timecode.
- `PreviewScrubBar` stays — it is a composition-time scrubber and works on audio.
- `StudioHeaderView`'s Export button is unchanged; only the format behind it changes (§7).

---

## 7. Export

New file, `Sources/Aura/Review/Export/ExportFormat.swift`:

```swift
/// What a session exports as. Derived from the timeline, not from the recording profile: a
/// screen recording whose video track came back empty must export as audio too, or the export
/// fails on an asset with nothing to encode.
enum ExportFormat: Equatable, Sendable {
    case video
    case audio

    init(timeline: ResolvedTimeline) {
        self = timeline.hasVideo ? .video : .audio
    }

    var fileExtension: String {
        switch self {
        case .video: return "mp4"
        case .audio: return "m4a"
        }
    }

    var contentType: UTType {
        switch self {
        case .video: return .mpeg4Movie
        case .audio: return .mpeg4Audio
        }
    }

    var fileType: AVFileType {
        switch self {
        case .video: return .mp4
        case .audio: return .m4a
        }
    }
}
```

`ExportEngine.export` gains the format:

```swift
func export(
    _ composition: BuiltComposition,
    as format: ExportFormat,
    to url: URL,
    onProgress: @escaping (ExportProgress) -> Void
) async throws
```

and `AVAssetExportEngine` picks its preset from it:

```swift
let presetName = switch format {
// Quality-based rather than a fixed-size HEVC preset, which would rescale a screen-native
// render size. (Unchanged reasoning.)
case .video: AVAssetExportPresetHEVCHighestQuality
// Audio-only: no video composition, no video encode. An asset with no video track cannot be
// exported with a video preset at all — the session reports unsupported.
case .audio: AVAssetExportPresetAppleM4A
}
…
if case .video = format { session.videoComposition = composition.videoComposition }
session.audioMix = composition.audioMix
session.timeRange = CMTimeRange(start: .zero, duration: composition.duration)
try await session.export(to: url, as: format.fileType)
```

`ReviewViewModel` exposes `var exportFormat: ExportFormat` (from `timeline`), and
`suggestedExportURL` uses `exportFormat.fileExtension`. `ExportButton.chooseDestination` uses
`[viewModel.exportFormat.contentType]` for `allowedContentTypes`.

`writeSubtitleSidecar(beside:)` needs no change: it derives the sidecar path from the
destination, so a podcast export writes `export.m4a` + `export.srt` — which is exactly the
agreed deliverable. Cuts and per-lane gain are applied by the same `audioMix` the preview uses,
so the exported audio matches what was heard.

---

## 8. Edge cases

| Case | Behaviour |
| --- | --- |
| Nothing selected | Start disabled with a reason; `start()` also guards and reports `.noSourcesSelected`. |
| Screen on, no display/window chosen | `RecordingRequest.isValid` false, Start disabled: `"Choose a display or window."` |
| System audio on, screen off | `ScreenCaptureSource` is constructed with `kinds == [.systemAudio]`; the stream attaches only the `.audio` output. The popover warns about the Screen Recording grant. |
| Permission refused for one source | `prepare()` throws before any session directory exists, so a refusal leaves no partial session behind — an improvement on today, where the directory is created first. |
| Camera unplugged mid-recording | Unchanged: the writer gets no more samples, `stop()` logs `track_failed`, the probe returns nil, and the editor opens without a camera lane. The manifest is what lets the studio say the camera *was* requested. |
| Camera requested, produced no frames | Same. Note this is what `TimelineResolver`'s screen-to-camera promotion already handles in the other direction. |
| Profile with no audio (screen only) | Transcript panel: `loadTranscript` already guards on a microphone probe (`ReviewViewModel.swift:1432`) and stays idle. Captions lane hides itself (no cues). Silence and filler actions must report unavailability rather than appear to work; `StudioAction.Availability.unavailable(reason:)` already exists for exactly this. |
| Profile with no video and no audio | Unreachable: `isRecordable` requires a non-empty set, and every `TrackKind` maps to a track. |
| Audio-only session, all tracks empty | `probes.isEmpty` → the existing `"This session has no readable media."` failure state. |
| Pre-Phase-6 sessions | Four files, no `recording.json`. `RecordingManifest.load` returns nil; everything else is probe-driven and unchanged. |
| `AURA_OPEN_SESSION` dev affordance | Unaffected. Worth pointing it at an audio-only session while building §6. |

---

## 9. Implementation order

Each step is independently shippable and leaves the app working.

1. **Model.** `RecordingProfile` (set-backed), `RecordingPreset`, `RecordingRequest`,
   `TrackKind: Codable` + `title`/`symbol`, `RecordingError.noSourcesSelected`. Pure; tests
   below. No behaviour change.
2. **`CaptureSource` protocol** + `CaptureContext` + `TrackSpec` + the shared `makeWriters`, and
   the two output-settings builders moved out of `RecordingController`. Nothing conforms yet.
3. **Conform the three existing sources**, one at a time, each with `RecordingController` still
   holding them as concrete properties. This is pure refactor: after each one, a full-studio
   recording must still open and play, with mic mute and screenshots working. `SystemAudioSink`
   is deleted with `ScreenCaptureSource`.
4. **Factory + controller fan-out.** `CaptureSourceFactory`, `start(_ request:)`,
   `checkDevicePermissions` deleted, source-list lifecycle. Drive it from the existing menu with
   `RecordingProfile.fullStudio` so behaviour is byte-identical, and verify pause/resume, stop,
   cancel, mute, screenshot and `track_start` offsets against a recording made before the
   change.
5. **Audio-only and video-only streams.** `ScreenCaptureSource(kinds:)` with one kind. **Verify
   on device** that an `.audio`-only stream starts; if it does not, fall back to attaching
   `.screen` and discarding (§2.2). Verify screen-only (no audio output) too.
6. **Manifest.** `RecordingManifest`, `SessionFolder.manifestURL`,
   `SessionManager.writeManifest`, the `record_start` label.
7. **Menu bar.** `RecordingSetupViewModel`, `RecordingProfileView` with its `ForEach` rows,
   `MicrophonePickerViewModel`, preferences. First point at which the feature is usable: record
   a podcast, a screen-only demo, a camera-only clip.
8. **Level meter.** `InputLevelMeter` (pure, tested) + `InputLevelMonitor`, popover-scoped, plus
   the in-recording level from `MicrophoneCaptureSource`.
9. **Audio stage.** Extract `AudioLaneWaveform`, extract `SourceAxisSurface`, add
   `AudioStageView`, hide the video-only controls. Manual checklist after the extraction, on a
   *video* session, because that is what the refactor can regress: click seeks; drag selects;
   double-click on a cut restores it; blade splits; marker drag still moves editorial markers
   only; pinch zooms; the scrollbar still appears on hover.
10. **Export format.** `ExportFormat`, engine preset selection, save-panel content type,
    suggested filename. Verify `export.m4a` + `export.srt` from a podcast session, and that
    video export is unchanged.
11. **Copy pass.** `StudioAction.shortenVideo`'s "Turn this into a short version" and similar
    video-assuming strings; unavailable reasons for the actions that need audio.

Steps 2–4 are the refactor, and they are ordered so that the source list arrives *after* every
source already works behind the protocol. The alternative — introducing the profile and the
protocol together — means a failure in step 4 is ambiguous between the two.

---

## 10. Tests

All pure, all in `Tests/AuraTests`, following the existing naming.

| File | Covers |
| --- | --- |
| `RecordingProfileTests` | `RecordingPreset.matching` round-trips every preset; a hand-built custom profile returns nil; `isRecordable` false only for the empty set; `needsScreenCaptureStream` true for screen-only, system-audio-only and both; `isAudioOnly`; `enabledKinds` is in `TrackKind.allCases` order regardless of insertion order; `set(_:enabled:)` is idempotent; `eventLabel` format. |
| `CaptureSourceFactoryTests` | Every preset produces the expected source count and the expected `kinds` union: podcast → one source writing `[.microphone]`; screen+system audio → **one** source writing `[.screen, .systemAudio]`; full studio → three sources covering all four kinds; camera-only → no `ScreenCaptureSource`; screen requested with no target → no source (and the request is invalid). This is the property a conditional recorder could not assert at all. |
| `RecordingRequestTests` | Screen on with no target is invalid; system-audio-only with no target is invalid; camera+mic with no target is valid; empty profile is invalid. |
| `TrackKindTests` | `title`/`symbol` agree with `TimelineLane` for the three overlapping lanes, so the picker and the timeline cannot drift apart; `Codable` raw values match the strings `events.jsonl` already writes. |
| `RecordingManifestTests` | Encode/decode round trip; the `tracks` array encodes as track-kind raw values; `load` from a file with unknown extra keys; `load` nil for a missing file and for malformed JSON. |
| `ExportFormatTests` | `.audio` for a timeline with `base == nil`; `.video` when a base exists; extension, content type and `AVFileType` pairs. |
| `InputLevelMeterTests` | Full scale is 1 and silence is 0 (at the floor); monotonic in between; attack moves faster than decay; a NaN or infinite RMS does not escape as a NaN level. |
| `TimelineResolverTests` (additions) | Audio-only probes → `base` nil, `hasVideo` false, `renderSize == fallbackRenderSize`, audio lanes still resolved; camera-only probes → camera is the base at the camera's even-floored size, `overlay` nil. |
| `SessionFolderTests` (addition) | `manifestURL` is `recording.json`; `load(rootURL:)` derives it for an existing folder. |

What stays untested, and knowingly: the three `CaptureSource` conformers' device code. It is
`AVCaptureSession` and `SCStream` plumbing that cannot run in a unit test, which is exactly why
selection (`CaptureSourceFactory`), profile derivation and writer specs were pulled out as pure
values — the parts a test can hold are now the parts that decide behaviour.

---

## Deferred

- **Audiogram video export** for podcasts (branded background, animated waveform, burned-in
  captions). A frame-generator layer — `CoreImage` waveform render into an `AVAssetWriter` — and
  it depends on caption styling that does not exist yet. The `.m4a` + `.srt` pair is what
  podcast hosts ingest; the social clip is a separate deliverable.
- **Burned-in captions.** Phase 5's reasoning is unchanged and still correct: they cannot be
  turned off after export, and the styling vocabulary has not settled.
- **Input monitoring to headphones.** Wanted for podcasting, but it needs a second audio stack
  (`AVAudioEngine` input → main mixer) and macOS offers no reliable way to know whether
  headphones are connected — so the failure mode is an acoustic feedback loop through the
  speakers of someone who just wanted to check their levels. Revisit with an explicit "I'm
  wearing headphones" confirmation, or once the meter has proven sufficient.
- **Multiple microphones / per-guest tracks.** The `CaptureSource` list makes the *recording*
  side of this nearly free — two `MicrophoneCaptureSource`s with different device ids — but
  `AudioLane` is a two-case enum threaded through `edit.json`, the projection, the compositor's
  audio mix and the timeline lanes. The editor side is its own phase, and `TrackKind` would have
  to carry an instance index.
- **Per-source pause.** Pausing only the camera mid-recording is expressible in `PauseClock` and
  now addressable per source, but not in the state machine, and nobody has asked.
- **Recording-time camera framing.** Cropping or zooming the camera while recording, as opposed
  to at edit time. Edit-time framing loses nothing, since the camera track is recorded at full
  resolution.
- **User-editable presets.** Five presets plus Custom covers the space; saved custom presets are
  a preference-management surface with no demand behind it yet.
