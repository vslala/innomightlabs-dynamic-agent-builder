import ScreenCaptureKit
import CoreMedia
import CoreVideo

/// Screen video and/or system audio: one `SCStream`, one or two tracks.
///
/// The only source that writes more than one track, because ScreenCaptureKit genuinely produces
/// both from a single stream. Splitting it into two sources would mean sharing one stream
/// between them with reference-counted start/stop — more machinery to express less truth.
final class ScreenCaptureSource: NSObject, CaptureSource, @unchecked Sendable {
    static let supportedKinds: Set<TrackKind> = [.screen, .systemAudio]
    /// 60, not 30: fast, continuous motion — game camera pans, particle effects — reads as
    /// visibly less smooth at half the temporal resolution, even when every frame that *is*
    /// captured lands cleanly. `minimumFrameInterval` is a floor, not a guarantee: a static
    /// desktop still delivers far fewer frames, since only genuinely new content produces one.
    static let captureFrameRate = 60

    private let target: CaptureTarget
    private let requested: Set<TrackKind>

    private var stream: SCStream?
    private let videoQueue = DispatchQueue(label: "com.innomightlabs.aura.screencapture.video")
    private let audioQueue = DispatchQueue(label: "com.innomightlabs.aura.screencapture.audio")

    var kinds: [TrackKind] { TrackKind.allCases.filter(requested.contains) }
    private(set) var writers: [TrackKind: TrackWriter] = [:]
    var onFailure: (@Sendable (Error) -> Void)?

    /// Last-write-wins cache of the most recent complete frame, for `screenshot()`. Written on
    /// the video queue, read on the main actor — `CVPixelBuffer` retain/release is thread-safe,
    /// so no lock is needed.
    private(set) var latestVideoFrame: CVPixelBuffer?

    private let droppedFrameCountLock = NSLock()
    private var _droppedFrameCount = 0
    /// Non-`.complete` frames ScreenCaptureKit delivered — idle/blank/suspended, or genuinely
    /// falling behind under load. Written on the video queue, read on the main actor.
    var droppedFrameCount: Int {
        droppedFrameCountLock.lock()
        defer { droppedFrameCountLock.unlock() }
        return _droppedFrameCount
    }

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

    func start(context: CaptureContext) async throws {
        var specs: [TrackSpec] = []
        if capturesVideo {
            specs.append(.video(
                kind: .screen,
                url: context.outputURL(for: .screen),
                pixelSize: target.pixelSize,
                frameRate: Self.captureFrameRate
            ))
        }
        if capturesAudio {
            specs.append(.audio(kind: .systemAudio, url: context.outputURL(for: .systemAudio)))
        }
        writers = try makeWriters(specs, context: context)

        let configuration = SCStreamConfiguration()
        // 8, not 5: more slack for ScreenCaptureKit to hold a frame while the writer is
        // momentarily busy, before it has to drop something upstream of `TrackWriter` — which
        // `droppedFrameCount` would otherwise report happening more than necessary.
        configuration.queueDepth = 8
        configuration.pixelFormat = kCVPixelFormatType_32BGRA
        configuration.showsCursor = true
        configuration.capturesAudio = capturesAudio
        configuration.excludesCurrentProcessAudio = true

        if capturesVideo {
            let pixelSize = target.pixelSize
            configuration.width = Int(pixelSize.width)
            configuration.height = Int(pixelSize.height)
            configuration.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(Self.captureFrameRate))
        } else {
            // ScreenCaptureKit has no audio-only stream: a filter and a configuration are
            // always required. No `.screen` output is attached below, so no frame is ever
            // delivered — but a display-sized configuration would still have the stream
            // allocate a buffer pool for pixels nobody reads. 2x2 at 1fps is the cheapest legal
            // configuration.
            configuration.width = 2
            configuration.height = 2
            configuration.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        }

        let stream = SCStream(filter: target.contentFilter(), configuration: configuration, delegate: self)
        if capturesVideo {
            try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: videoQueue)
        }
        if capturesAudio {
            try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: audioQueue)
        }
        try await stream.startCapture()
        self.stream = stream
    }

    func stop() async {
        guard let stream else { return }
        try? await stream.stopCapture()
        self.stream = nil
    }

    func cancel() {
        stream = nil
    }
}

extension ScreenCaptureSource: SCStreamOutput {
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard CMSampleBufferDataIsReady(sampleBuffer) else { return }
        switch type {
        case .screen:
            // ScreenCaptureKit also delivers periodic non-.complete frames (idle/blank/
            // suspended/started) with no real new pixel data whenever the screen content
            // isn't actively changing. Appending one of those to AVAssetWriterInput
            // corrupts the encoder pipeline, so only forward genuinely complete frames.
            // Counted regardless — mostly benign during an idle desktop, but a source worth
            // checking first if a *constantly* rendering capture (a game) still turns out
            // choppy despite the frame-rate fix above.
            guard Self.isCompleteFrame(sampleBuffer) else {
                droppedFrameCountLock.lock()
                _droppedFrameCount += 1
                droppedFrameCountLock.unlock()
                return
            }
            if let imageBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) {
                latestVideoFrame = imageBuffer
            }
            writers[.screen]?.append(sampleBuffer)
        case .audio:
            writers[.systemAudio]?.append(sampleBuffer)
        default:
            break
        }
    }

    private static func isCompleteFrame(_ sampleBuffer: CMSampleBuffer) -> Bool {
        guard let attachmentsArray = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
              let attachments = attachmentsArray.first,
              let statusRawValue = attachments[.status] as? Int,
              let status = SCFrameStatus(rawValue: statusRawValue) else {
            return false
        }
        return status == .complete
    }
}

extension ScreenCaptureSource: SCStreamDelegate {
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        onFailure?(error)
    }
}
