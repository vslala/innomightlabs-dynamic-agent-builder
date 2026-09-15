import AVFoundation
import CoreMedia
import CoreVideo
import Foundation

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

    /// Paused time already elapsed before this source existed. Zero for every source created
    /// at `RecordingController.start`; non-zero only for one added later by a live profile
    /// switch, after the session was paused and resumed at least once already. See
    /// `PauseClock.init`.
    var elapsedPausedDuration: CMTime = .zero

    /// The on-window ("segment") index each kind is about to write, so a track that was
    /// switched off and back on gets its own file rather than resuming the finished one.
    /// Absent kinds default to `0` — the same file name a session that never switches uses.
    private var segmentIndices: [TrackKind: Int] = [:]

    init(
        folder: SessionFolder,
        sessionStartTime: CMTime,
        elapsedPausedDuration: CMTime = .zero,
        segmentIndices: [TrackKind: Int] = [:]
    ) {
        self.folder = folder
        self.sessionStartTime = sessionStartTime
        self.elapsedPausedDuration = elapsedPausedDuration
        self.segmentIndices = segmentIndices
    }

    /// The file a source should write `kind` into. A source asks for its own file rather than
    /// naming one itself, so the segment-numbering rule has exactly one owner.
    func outputURL(for kind: TrackKind) -> URL {
        folder.url(for: kind, segment: segmentIndices[kind] ?? 0)
    }
}

/// One recordable device, owning its device session, its `TrackWriter`s and its own callback
/// wiring.
///
/// `RecordingController` composes a list of these from the profile and fans the lifecycle over
/// it, so adding or removing a recordable source is one conformer and one line in
/// `CaptureSourceFactory` — not a branch in five methods.
///
/// Classes, and `@unchecked Sendable` like the implementations already are: each owns a
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
    ///
    /// `async` because `ScreenCaptureSource` must await `SCStream.startCapture()` to propagate
    /// a rejected configuration synchronously — a fire-and-forget start would let the
    /// controller reach `.recording` on a stream that never actually started. The
    /// `AVCaptureSession`-backed sources have nothing to await; they simply don't suspend.
    func start(context: CaptureContext) async throws

    func stop() async
    func cancel()

    /// Muting is a property of sources that can be muted. A default no-op is what lets the
    /// controller say `sources.forEach { $0.setMuted(true) }` without asking which is the mic.
    func setMuted(_ muted: Bool)

    /// The most recent full frame, for `screenshot()`. Default nil.
    var latestVideoFrame: CVPixelBuffer? { get }

    /// Frames dropped before ever reaching a writer — e.g. ScreenCaptureKit delivering a
    /// non-`.complete` frame during heavy system load. Zero for sources that cannot drop
    /// upstream of their writers. Read once, at retirement, purely for diagnostics: logging
    /// per drop would itself be a performance problem under the load that causes drops.
    var droppedFrameCount: Int { get }
}

extension CaptureSource {
    func setMuted(_ muted: Bool) {}
    var latestVideoFrame: CVPixelBuffer? { nil }
    var droppedFrameCount: Int { 0 }
}

/// Everything needed to create one `TrackWriter`, as a value — so a source declares its tracks
/// and a single shared function builds them.
struct TrackSpec {
    let kind: TrackKind
    let outputURL: URL
    let outputFileType: AVFileType
    let outputSettings: [String: Any]

    /// `frameRate` is an encoder hint, not an enforced cadence — real frames still land at
    /// whatever their own presentation timestamps say. It drives keyframe spacing (one per
    /// second of `frameRate` frames) and the encoder's bitrate planning, so it should match
    /// what the source actually delivers: 60 for `ScreenCaptureSource`, once its
    /// `minimumFrameInterval` allows that; the camera's default of 30 matches what most
    /// webcams deliver at the presets `CameraCaptureSource` requests.
    static func video(kind: TrackKind, url: URL, pixelSize: CGSize, frameRate: Int = 30) -> TrackSpec {
        TrackSpec(
            kind: kind,
            outputURL: url,
            outputFileType: .mov,
            outputSettings: [
                AVVideoCodecKey: AVVideoCodecType.hevc,
                AVVideoWidthKey: Int(pixelSize.width),
                AVVideoHeightKey: Int(pixelSize.height),
                AVVideoCompressionPropertiesKey: [
                    AVVideoExpectedSourceFrameRateKey: frameRate,
                    AVVideoMaxKeyFrameIntervalKey: frameRate
                ] as [String: Any]
            ]
        )
    }

    static func audio(kind: TrackKind, url: URL) -> TrackSpec {
        TrackSpec(
            kind: kind,
            outputURL: url,
            outputFileType: .m4a,
            outputSettings: [
                AVFormatIDKey: kAudioFormatMPEG4AAC,
                AVNumberOfChannelsKey: 2,
                AVSampleRateKey: 44_100,
                AVEncoderBitRateKey: 128_000
            ]
        )
    }
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
                sessionStartTime: context.sessionStartTime,
                elapsedPausedDuration: context.elapsedPausedDuration
            )
            try writer.start()
            writers[spec.kind] = writer
        }
        return writers
    }
}
