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
    @Published private(set) var currentProfile: RecordingProfile?

    /// Called once a session's files are finalized, so a review window can open over it.    /// A callback rather than a published property because `stop()` completes asynchronously
    /// after the menu that started it has already been dismissed — there is no view alive at
    /// that moment to observe a change.
    var onSessionCompleted: ((SessionFolder) -> Void)?

    /// One entry per enabled track, in whatever order `CaptureSourceFactory` created them —
    /// not `TrackKind.allCases` order. Anything needing that order goes through `writersByKind`.
    private var sources: [any CaptureSource] = []

    private var sessionManager: SessionManager?
    private var sessionStartTime: CMTime = .zero

    /// Mirrors the paused duration every `TrackWriter`'s `PauseClock` accumulates —
    /// `pause`/`resume` fan one host time out to all of them, so this stays in lockstep.
    /// Without it, logged events would sit on a different clock than the recorded media.
    private var accumulatedPausedDuration: CMTime = .zero
    private var pauseStartedAt: CMTime?

    /// Every writer across every source, ordered by `TrackKind.allCases` so writer teardown,
    /// the `track_start` events and `pause`/`resume` fan-out are deterministic regardless of
    /// which order the sources were constructed in.
    private var writersByKind: [(TrackKind, TrackWriter)] {
        let merged = sources.reduce(into: [TrackKind: TrackWriter]()) { result, source in
            result.merge(source.writers) { existing, _ in existing }
        }
        return TrackKind.allCases.compactMap { kind in merged[kind].map { (kind, $0) } }
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

            for source in sources {
                source.onFailure = { [weak self] error in
                    Task { @MainActor [weak self] in
                        self?.handleSourceFailure(error)
                    }
                }
                try await source.start(context: context)
            }

            try manager.writeManifest(RecordingManifest(
                profile: request.profile,
                startedAt: Date(),
                screenTargetName: request.profile.tracks.contains(.screen) ? request.screenTarget?.displayName : nil
            ))

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

        for source in sources { await source.stop() }

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
        sources.forEach { $0.setMuted(true) }
    }

    func unmute() {
        guard state == .recording || state == .paused else { return }
        sources.forEach { $0.setMuted(false) }
    }

    func mark(label: String) {
        guard state == .recording || state == .paused else { return }
        let hostTime = CMClockGetTime(CMClockGetHostTimeClock())
        logEvent(.userMarker, at: hostTime, label: label)
    }

    func screenshot() async {
        guard state == .recording || state == .paused else { return }
        // Screen before camera, so screen wins when both are recording and a camera-only
        // session gets screenshots for free.
        let videoKinds: [TrackKind] = [.screen, .camera]
        let pixelBuffer = videoKinds
            .lazy
            .compactMap { kind in self.sources.first { $0.kinds.contains(kind) }?.latestVideoFrame }
            .first
        guard let pixelBuffer, let sessionManager else { return }

        let hostTime = CMClockGetTime(CMClockGetHostTimeClock())
        let ts = elapsed(hostTime)
        let filename = String(format: "%.1f.png", ts)
        let fileURL = sessionManager.folder.screenshotsURL.appendingPathComponent(filename)

        guard Self.writePNG(pixelBuffer: pixelBuffer, to: fileURL) else { return }
        logEvent(.screenSnapshot, at: hostTime, path: "screenshots/\(filename)")
    }

    func cancel() async {
        guard applyTransition(.cancel) else { return }

        for source in sources { source.cancel() }
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

    private func handleSourceFailure(_ error: Error) {
        guard state == .recording || state == .paused else { return }
        lastError = .captureStreamStopped(error.localizedDescription)
        Task { await stop() }
    }

    private func rollbackFailedStart() async {
        for source in sources { source.cancel() }
        tearDownSessionState()
        applyTransition(.startFailed)
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
}
