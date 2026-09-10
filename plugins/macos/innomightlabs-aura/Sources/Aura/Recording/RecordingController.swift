import AVFoundation
import CoreImage
import CoreMedia
import Foundation
import ImageIO

@MainActor
final class RecordingController: ObservableObject {
    @Published private(set) var state: RecordingState = .idle
    @Published var lastError: RecordingError?
    @Published private(set) var currentTargetName: String?

    /// Called once a session's files are finalized, so a review window can open over it.    /// A callback rather than a published property because `stop()` completes asynchronously
    /// after the menu that started it has already been dismissed — there is no view alive at
    /// that moment to observe a change.
    var onSessionCompleted: ((SessionFolder) -> Void)?

    private let screenCaptureSession = ScreenCaptureSession()
    private let cameraRecorder = CameraRecorder()
    private let microphoneRecorder = MicrophoneRecorder()

    private var sessionManager: SessionManager?
    private var sessionStartTime: CMTime = .zero

    /// Mirrors the paused duration every `TrackWriter`'s `PauseClock` accumulates —
    /// `pause`/`resume` fan one host time out to all of them, so this stays in lockstep.
    /// Without it, logged events would sit on a different clock than the recorded media.
    private var accumulatedPausedDuration: CMTime = .zero
    private var pauseStartedAt: CMTime?

    private var screenWriter: TrackWriter?
    private var cameraWriter: TrackWriter?
    private var microphoneWriter: TrackWriter?
    private var systemAudioWriter: TrackWriter?
    private var systemAudioSink: SystemAudioSink?

    /// Written only on the main actor, read from the mic capture queue in `wireCallbacks`.
    /// A stale read for one buffer is harmless (worst case one extra/missing sample at the
    /// mute boundary) — unlike `PauseClock`, exact correctness isn't required here.
    private var isMicMuted = false

    /// Last-write-wins cache of the most recent complete screen frame, for `screenshot()`.
    /// Written from the video capture queue, read on the main actor — `CVPixelBuffer`
    /// retain/release is thread-safe, so no lock is needed.
    private var latestVideoPixelBuffer: CVPixelBuffer?

    private var allTrackWriters: [TrackWriter] {
        [screenWriter, cameraWriter, microphoneWriter, systemAudioWriter].compactMap { $0 }
    }

    private var writersByKind: [(TrackKind, TrackWriter)] {
        [
            (.screen, screenWriter), (.camera, cameraWriter),
            (.microphone, microphoneWriter), (.systemAudio, systemAudioWriter)
        ].compactMap { kind, writer in writer.map { (kind, $0) } }
    }

    func start(target: CaptureTarget, cameraDeviceID: String? = nil) async {
        guard applyTransition(.start) else { return }

        do {
            try await checkDevicePermissions()

            let manager = SessionManager()
            try manager.createSessionDirectory()

            let startTime = CMClockGetTime(CMClockGetHostTimeClock())

            let screenWriter = try TrackWriter(
                outputURL: manager.folder.screenURL,
                outputFileType: .mov,
                mediaType: .video,
                outputSettings: Self.videoOutputSettings(pixelSize: target.pixelSize),
                sessionStartTime: startTime
            )
            let cameraSize = CameraRecorder.devicePixelSize(deviceID: cameraDeviceID) ?? CGSize(width: 1280, height: 720)
            let cameraWriter = try TrackWriter(
                outputURL: manager.folder.cameraURL,
                outputFileType: .mov,
                mediaType: .video,
                outputSettings: Self.videoOutputSettings(pixelSize: cameraSize),
                sessionStartTime: startTime
            )
            let microphoneWriter = try TrackWriter(
                outputURL: manager.folder.microphoneURL,
                outputFileType: .m4a,
                mediaType: .audio,
                outputSettings: Self.audioOutputSettings(),
                sessionStartTime: startTime
            )
            let systemAudioWriter = try TrackWriter(
                outputURL: manager.folder.systemAudioURL,
                outputFileType: .m4a,
                mediaType: .audio,
                outputSettings: Self.audioOutputSettings(),
                sessionStartTime: startTime
            )

            try screenWriter.start()
            try cameraWriter.start()
            try microphoneWriter.start()
            try systemAudioWriter.start()

            self.sessionManager = manager
            self.sessionStartTime = startTime
            self.screenWriter = screenWriter
            self.cameraWriter = cameraWriter
            self.microphoneWriter = microphoneWriter
            self.systemAudioWriter = systemAudioWriter
            self.systemAudioSink = SystemAudioSink(trackWriter: systemAudioWriter)

            wireCallbacks(
                screenWriter: screenWriter,
                cameraWriter: cameraWriter,
                microphoneWriter: microphoneWriter
            )

            try await screenCaptureSession.start(target: target)
            try cameraRecorder.start(deviceID: cameraDeviceID)
            try microphoneRecorder.start()

            currentTargetName = target.displayName
            logEvent(.recordStart, at: startTime, app: target.displayName)
            applyTransition(.didStart)
        } catch let error as RecordingError {
            await rollbackFailedStart()
            lastError = error
        } catch {
            await rollbackFailedStart()
            lastError = .writerSetupFailed(error.localizedDescription)
        }
    }

    func pause() {
        guard applyTransition(.pause) else { return }
        let hostTime = CMClockGetTime(CMClockGetHostTimeClock())
        allTrackWriters.forEach { $0.pause(at: hostTime) }
        if pauseStartedAt == nil {
            pauseStartedAt = hostTime
        }
        logEvent(.pause, at: hostTime)
    }

    func resume() {
        guard applyTransition(.resume) else { return }
        let hostTime = CMClockGetTime(CMClockGetHostTimeClock())
        allTrackWriters.forEach { $0.resume(at: hostTime) }
        if let pauseStartedAt {
            accumulatedPausedDuration = accumulatedPausedDuration + (hostTime - pauseStartedAt)
            self.pauseStartedAt = nil
        }
        logEvent(.resume, at: hostTime)
    }

    func stop() async {
        guard applyTransition(.stop) else { return }

        let hostTime = CMClockGetTime(CMClockGetHostTimeClock())
        logEvent(.recordStop, at: hostTime)

        cameraRecorder.stop()
        microphoneRecorder.stop()
        try? await screenCaptureSession.stop()

        // Recorded before teardown: this is what lets the review layer realign a track whose
        // warm-up offset `AVAssetWriter` discarded (which it does for every audio track).
        logTrackStartOffsets()

        let writers = allTrackWriters
        await finishWriters()
        let failures = writers.compactMap(\.failureReason)
        // Recorded into the log so the review window knows a track is expected-missing
        // rather than having to guess why an asset won't load.
        failures.forEach { logEvent(.trackFailed, at: hostTime, label: $0) }
        if !failures.isEmpty {
            lastError = .writerSetupFailed(failures.joined(separator: "; "))
        }

        let completedSession = sessionManager?.folder
        tearDownSessionState()

        applyTransition(.didStop)

        // After the transition, so the recorder is idle by the time the review window appears.
        if let completedSession {
            onSessionCompleted?(completedSession)
        }
    }

    func mute() {
        guard state == .recording || state == .paused else { return }
        isMicMuted = true
    }

    func unmute() {
        guard state == .recording || state == .paused else { return }
        isMicMuted = false
    }

    func mark(label: String) {
        guard state == .recording || state == .paused else { return }
        let hostTime = CMClockGetTime(CMClockGetHostTimeClock())
        logEvent(.userMarker, at: hostTime, label: label)
    }

    func screenshot() async {
        guard state == .recording || state == .paused else { return }
        guard let pixelBuffer = latestVideoPixelBuffer, let sessionManager else { return }

        let hostTime = CMClockGetTime(CMClockGetHostTimeClock())
        let ts = elapsed(hostTime)
        let filename = String(format: "%.1f.png", ts)
        let fileURL = sessionManager.folder.screenshotsURL.appendingPathComponent(filename)

        guard Self.writePNG(pixelBuffer: pixelBuffer, to: fileURL) else { return }
        logEvent(.screenSnapshot, at: hostTime, path: "screenshots/\(filename)")
    }

    func cancel() async {
        guard applyTransition(.cancel) else { return }

        cameraRecorder.stop()
        microphoneRecorder.stop()
        try? await screenCaptureSession.stop()

        allTrackWriters.forEach { $0.cancel() }

        let rootURL = sessionManager?.folder.rootURL
        tearDownSessionState()
        if let rootURL {
            try? FileManager.default.removeItem(at: rootURL)
        }

        applyTransition(.didStop)
    }

    private static func writePNG(pixelBuffer: CVPixelBuffer, to url: URL) -> Bool {
        let ciImage = CIImage(cvPixelBuffer: pixelBuffer)
        guard let cgImage = CIContext().createCGImage(ciImage, from: ciImage.extent) else { return false }
        guard let destination = CGImageDestinationCreateWithURL(url as CFURL, "public.png" as CFString, 1, nil) else {
            return false
        }
        CGImageDestinationAddImage(destination, cgImage, nil)
        return CGImageDestinationFinalize(destination)
    }

    private func wireCallbacks(screenWriter: TrackWriter, cameraWriter: TrackWriter, microphoneWriter: TrackWriter) {
        screenCaptureSession.onVideoSampleBuffer = { [weak self, weak screenWriter] buffer in
            if let imageBuffer = CMSampleBufferGetImageBuffer(buffer) {
                self?.latestVideoPixelBuffer = imageBuffer
            }
            screenWriter?.append(buffer)
        }
        screenCaptureSession.onAudioSampleBuffer = { [weak self] buffer in
            self?.systemAudioSink?.handle(buffer)
        }
        screenCaptureSession.onStreamStopped = { [weak self] error in
            Task { @MainActor [weak self] in
                self?.handleStreamFailure(error)
            }
        }
        cameraRecorder.onSampleBuffer = { [weak cameraWriter] buffer in
            cameraWriter?.append(buffer)
        }
        microphoneRecorder.onSampleBuffer = { [weak self, weak microphoneWriter] buffer in
            guard self?.isMicMuted != true else { return }
            microphoneWriter?.append(buffer)
        }
    }

    private func handleStreamFailure(_ error: Error) {
        guard state == .recording || state == .paused else { return }
        lastError = .captureStreamStopped(error.localizedDescription)
        Task { await stop() }
    }

    private func rollbackFailedStart() async {
        cameraRecorder.stop()
        microphoneRecorder.stop()
        try? await screenCaptureSession.stop()
        tearDownSessionState()
        applyTransition(.startFailed)
    }

    private func tearDownSessionState() {
        sessionManager?.close()
        sessionManager = nil
        screenWriter = nil
        cameraWriter = nil
        microphoneWriter = nil
        systemAudioWriter = nil
        systemAudioSink = nil
        currentTargetName = nil
        isMicMuted = false
        latestVideoPixelBuffer = nil
        accumulatedPausedDuration = .zero
        pauseStartedAt = nil
    }

    private func finishWriters() async {
        let writers = allTrackWriters
        await withTaskGroup(of: Void.self) { group in
            for writer in writers {
                group.addTask {
                    await withCheckedContinuation { continuation in
                        writer.finish { continuation.resume() }
                    }
                }
            }
        }
    }

    private func checkDevicePermissions() async throws {
        let cameraStatus = AVCaptureDevice.authorizationStatus(for: .video)
        if cameraStatus == .notDetermined {
            guard await AVCaptureDevice.requestAccess(for: .video) else {
                throw RecordingError.cameraPermissionDenied
            }
        } else if cameraStatus != .authorized {
            throw RecordingError.cameraPermissionDenied
        }

        let micStatus = AVCaptureDevice.authorizationStatus(for: .audio)
        if micStatus == .notDetermined {
            guard await AVCaptureDevice.requestAccess(for: .audio) else {
                throw RecordingError.microphonePermissionDenied
            }
        } else if micStatus != .authorized {
            throw RecordingError.microphonePermissionDenied
        }
        // Screen Recording has no pre-flight authorization API; a denied/not-yet-granted
        // state surfaces instead as SCShareableContent.current throwing in the picker,
        // or SCStream.startCapture() throwing above.
    }

    @discardableResult
    private func applyTransition(_ trigger: RecordingEventTrigger) -> Bool {
        switch RecordingStateMachine.transition(current: state, trigger: trigger) {
        case .success(let newState):
            state = newState
            return true
        case .failure:
            return false
        }
    }

    /// One `track_start` per track, carrying how far behind the shared session start that
    /// track's first sample actually was.
    private func logTrackStartOffsets() {
        for (kind, writer) in writersByKind {
            guard let firstSample = writer.firstAppendedHostTime else { continue }
            let offset = max(0, CMTimeGetSeconds(firstSample - sessionStartTime))
            sessionManager?.logEvent(RecordingEvent(
                ts: offset,
                type: .trackStart,
                mediaTs: offset,
                label: kind.rawValue
            ))
        }
    }

    private func logEvent(
        _ type: RecordingEventKind,
        at hostTime: CMTime,
        app: String? = nil,
        label: String? = nil,
        path: String? = nil
    ) {
        sessionManager?.logEvent(RecordingEvent(
            ts: elapsed(hostTime),
            type: type,
            mediaTs: mediaElapsed(hostTime),
            app: app,
            label: label,
            path: path
        ))
    }

    private func elapsed(_ hostTime: CMTime) -> TimeInterval {
        CMTimeGetSeconds(hostTime - sessionStartTime)
    }

    /// Elapsed time on the pause-compacted timeline the media files are written on:
    /// wall-clock elapsed minus every completed pause, and frozen at the pause point for
    /// anything logged while paused (that span doesn't exist in the files).
    private func mediaElapsed(_ hostTime: CMTime) -> TimeInterval {
        let effective = pauseStartedAt ?? hostTime
        return max(0, CMTimeGetSeconds(effective - sessionStartTime - accumulatedPausedDuration))
    }

    private static func videoOutputSettings(pixelSize: CGSize) -> [String: Any] {
        [
            AVVideoCodecKey: AVVideoCodecType.hevc,
            AVVideoWidthKey: Int(pixelSize.width),
            AVVideoHeightKey: Int(pixelSize.height),
            AVVideoCompressionPropertiesKey: [
                AVVideoExpectedSourceFrameRateKey: 30,
                AVVideoMaxKeyFrameIntervalKey: 30
            ] as [String: Any]
        ]
    }

    private static func audioOutputSettings() -> [String: Any] {
        [
            AVFormatIDKey: kAudioFormatMPEG4AAC,
            AVNumberOfChannelsKey: 2,
            AVSampleRateKey: 44_100,
            AVEncoderBitRateKey: 128_000
        ]
    }
}
