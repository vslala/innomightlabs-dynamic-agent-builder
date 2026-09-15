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

    /// What `sources` was built from, minus the profile — kept so `switchProfile` needs only a
    /// new profile and never has to ask the caller to resupply the screen target or device ids.
    private var activeRequest: RecordingRequest?

    /// The next on-window ("segment") index to use per kind. Absent means `0`, which is also
    /// what a session that never switches profiles uses throughout — see `SessionFolder`.
    private var segmentCounts: [TrackKind: Int] = [:]

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
            self.sessionManager = manager
            self.sessionStartTime = startTime
            // Assigned before starting, not after: a source that throws partway through the
            // loop below is handled by `rollbackFailedStart`, which cancels every entry in
            // `self.sources` — including ones that had not started yet. Assigning only on
            // success would leave those already-begun sources uncancelled on partial failure.
            self.sources = sources
            let context = makeContext(folder: manager.folder)

            for source in sources {
                source.onFailure = makeFailureHandler()
                try await source.start(context: context)
            }
            advanceSegmentCounts(for: sources.flatMap { $0.kinds })
            activeRequest = request

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

    /// Replaces the live profile without interrupting the sources it has in common with the
    /// new one — the camera and microphone keep recording into the same files while the screen
    /// is switched on or off around them.
    ///
    /// Added sources are prepared *and started* before anything already running is retired, so
    /// a refused permission prompt or a rejected `SCStream` configuration leaves the recording
    /// exactly as it was. That ordering is the whole reason this is not one loop over the diff.
    func switchProfile(to profile: RecordingProfile) async {
        guard state == .recording, let activeRequest, let folder = sessionManager?.folder else { return }

        let request = activeRequest.replacing(profile: profile)
        guard request.isValid else {
            lastError = profile.isRecordable
                ? .writerSetupFailed("Choose a display or window to record.")
                : .noSourcesSelected
            return
        }

        let plan = CaptureSourceFactory.plan(live: sources, for: request)
        guard !plan.isEmpty else { return }

        let context = makeContext(folder: folder)
        do {
            for source in plan.added {
                try await source.prepare()
            }
            for source in plan.added {
                source.onFailure = makeFailureHandler()
                try await source.start(context: context)
            }
        } catch {
            // No-op on failure: `sources` was never touched, so only what this call itself
            // started needs undoing.
            plan.added.forEach { $0.cancel() }
            lastError = (error as? RecordingError) ?? .writerSetupFailed(error.localizedDescription)
            return
        }

        let failures = await retire(plan.removed)
        sources = plan.resulting
        advanceSegmentCounts(for: plan.added.flatMap { $0.kinds })
        self.activeRequest = request
        currentProfile = profile

        let hostTime = CMClockGetTime(CMClockGetHostTimeClock())
        failures.forEach { logEvent(.trackFailed, at: hostTime, label: $0) }
        if !failures.isEmpty {
            lastError = .writerSetupFailed(failures.joined(separator: "; "))
        }
        logEvent(.profileChanged, at: hostTime, label: profile.eventLabel)
    }

    func stop() async {
        guard applyTransition(.stop) else { return }

        let hostTime = CMClockGetTime(CMClockGetHostTimeClock())
        logEvent(.recordStop, at: hostTime)

        let failures = await retire(sources)
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
        activeRequest = nil
        segmentCounts = [:]
        currentTargetName = nil
        currentProfile = nil
        accumulatedPausedDuration = .zero
        pauseStartedAt = nil
    }

    /// Stops capturing, records where each retiring track's file actually began, and
    /// finalizes its files. Returns each failed writer's reason, if any.
    ///
    /// Two phases rather than one loop per source: every device should stop at as nearly the
    /// same instant as possible, and only once every source has stopped is it safe to
    /// finalize — finishing one writer while a sibling source is still mid-callback would race
    /// the finalize against a buffer still in flight.
    ///
    /// Shared by `stop()` (retiring every source) and `switchProfile` (retiring only the ones
    /// the new profile drops), so the two can never log offsets or finalize differently.
    private func retire(_ retiring: [any CaptureSource]) async -> [String] {
        for source in retiring { await source.stop() }

        let writers = retiring.flatMap { source in source.writers.map { ($0.key, $0.value) } }
        logTrackStartOffsets(of: writers)
        logDroppedFrames(sources: retiring, writers: writers)
        await finish(writers.map(\.1))
        return writers.compactMap { $0.1.failureReason }
    }

    /// One diagnostic event per kind that dropped anything, logged once here rather than per
    /// frame — logging every frame would itself become a performance problem under exactly
    /// the load that causes drops. See `CaptureSource.droppedFrameCount` and
    /// `TrackWriter.droppedSampleCount`.
    private func logDroppedFrames(sources: [any CaptureSource], writers: [(TrackKind, TrackWriter)]) {
        let hostTime = CMClockGetTime(CMClockGetHostTimeClock())
        for source in sources where source.droppedFrameCount > 0 {
            let kinds = source.kinds.map(\.rawValue).joined(separator: "+")
            logEvent(.framesDropped, at: hostTime, label: "\(kinds):upstream=\(source.droppedFrameCount)")
        }
        for (kind, writer) in writers where writer.droppedSampleCount > 0 {
            logEvent(.framesDropped, at: hostTime, label: "\(kind.rawValue):backpressure=\(writer.droppedSampleCount)")
        }
    }

    private func finish(_ writers: [TrackWriter]) async {
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

    /// The context a source being (re)started should use: the shared session clock, how much
    /// pause time already elapsed, and which on-window each kind is about to write.
    private func makeContext(folder: SessionFolder) -> CaptureContext {
        CaptureContext(
            folder: folder,
            sessionStartTime: sessionStartTime,
            elapsedPausedDuration: accumulatedPausedDuration,
            segmentIndices: segmentCounts
        )
    }

    private func advanceSegmentCounts(for kinds: [TrackKind]) {
        for kind in kinds {
            segmentCounts[kind, default: 0] += 1
        }
    }

    private func makeFailureHandler() -> @Sendable (Error) -> Void {
        { [weak self] error in
            Task { @MainActor [weak self] in
                self?.handleSourceFailure(error)
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

    /// One `track_start` per writer, carrying how far behind the shared session start its
    /// file's first sample actually was, and which file it belongs to.
    ///
    /// Takes the writers explicitly rather than reading `writersByKind`, which reflects only
    /// the *live* source list — a writer retired mid-session is already gone from it by the
    /// time this runs, and a segment logged with no offset plays from zero, which for audio
    /// means early by the entire time it was not recording.
    private func logTrackStartOffsets(of writers: [(TrackKind, TrackWriter)]) {
        for (kind, writer) in writers {
            guard let firstSample = writer.firstAppendedHostTime else { continue }
            let offset = max(0, CMTimeGetSeconds(firstSample - sessionStartTime))
            sessionManager?.logEvent(RecordingEvent(
                ts: offset,
                type: .trackStart,
                mediaTs: offset,
                label: kind.rawValue,
                path: writer.outputURL.lastPathComponent
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
