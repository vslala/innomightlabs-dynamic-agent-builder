import AVFoundation
import CoreImage
import CoreMedia
import Foundation
import ImageIO

@MainActor
final class RecordingController: ObservableObject, BrowserTakeRecording {
    @Published private(set) var state: RecordingState = .idle
    @Published var lastError: RecordingError?
    @Published private(set) var currentTargetName: String?
    @Published private(set) var currentProfile: RecordingProfile?
    /// Set while the current recording has a track whose signal looks corrupted, so the menu
    /// bar icon can say so even with the popover closed. Cleared when the session ends;
    /// `lastError` keeps the explanation afterwards.
    @Published private(set) var signalWarning: String?

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
    private var pendingBrowserTakeResult: (status: BrowserTakeMetadata.Status, failureReason: String?)?
    private var browserTakeFinalizationFailed = false
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

    var currentSessionFolder: SessionFolder? { sessionManager?.folder }

    func currentSessionTime() -> TimeInterval? {
        guard state == .recording || state == .paused else { return nil }
        return mediaElapsed(CMClockGetTime(CMClockGetHostTimeClock()))
    }

    func browserStep(label: String) {
        guard state == .recording else { return }
        logEvent(.browserStep, at: CMClockGetTime(CMClockGetHostTimeClock()), label: label)
    }

    func start(_ request: RecordingRequest, prepareSession: ((SessionFolder) throws -> Void)? = nil) async {
        guard request.isValid else {
            lastError = request.profile.isRecordable
                ? .writerSetupFailed("Choose a display or window to record.")
                : .noSourcesSelected
            return
        }
        guard applyTransition(.start) else { return }
        browserTakeFinalizationFailed = false

        let sources = CaptureSourceFactory.sources(for: request)

        do {
            // Permission prompts and device configuration, before a session directory exists —
            // so a refusal leaves nothing behind.
            for source in sources {
                try await source.prepare()
                try Task.checkCancellation()
            }

            let manager = SessionManager()
            try manager.createSessionDirectory()
            self.sessionManager = manager
            try manager.writeManifest(RecordingManifest(
                profile: request.profile,
                startedAt: Date(),
                screenTargetName: request.profile.tracks.contains(.screen) ? request.screenTarget?.displayName : nil,
                browserTake: request.browserTake
            ))
            try prepareSession?(manager.folder)
            try Task.checkCancellation()

            let startTime = CMClockGetTime(CMClockGetHostTimeClock())
            self.sessionStartTime = startTime
            // Assigned before starting, not after: a source that throws partway through the
            // loop below is handled by `rollbackFailedStart`, which cancels every entry in
            // `self.sources` — including ones that had not started yet. Assigning only on
            // success would leave those already-begun sources uncancelled on partial failure.
            self.sources = sources
            let context = makeContext(folder: manager.folder)

            for source in sources {
                source.onFailure = makeFailureHandler()
                source.onNotice = makeNoticeHandler()
                try await source.start(context: context)
                try Task.checkCancellation()
            }
            advanceSegmentCounts(for: sources.flatMap { $0.kinds })
            activeRequest = request

            currentProfile = request.profile
            currentTargetName = request.profile.tracks.contains(.screen) ? request.screenTarget?.displayName : nil
            logEvent(.recordStart, at: startTime, app: currentTargetName, label: request.profile.eventLabel)
            applyTransition(.didStart)
        } catch is CancellationError {
            await rollbackFailedStart()
        } catch let error as RecordingError {
            await rollbackFailedStart()
            lastError = error
        } catch {
            await rollbackFailedStart()
            lastError = .writerSetupFailed(error.localizedDescription)
        }
    }

    func startBrowserTake(_ request: RecordingRequest, spec: DemoSpec, viewport: BrowserViewportMetadata) async throws -> SessionFolder {
        guard state == .idle else { throw ReplayError.recorderBusy }
        await start(request, prepareSession: { folder in
            try JSONEncoder().encode(spec).write(to: folder.demoSpecURL, options: .atomic)
            try JSONEncoder().encode(viewport).write(to: folder.viewportURL, options: .atomic)
            try Data().write(to: folder.actionLogJournalURL, options: .atomic)
        })
        guard state == .recording, let folder = currentSessionFolder else {
            throw ReplayError.recordingInterrupted
        }
        return folder
    }

    /// Must precede host interruption, including task cancellation: the host can close its
    /// window as soon as cancellation reaches an in-flight command.
    func prepareToStopBrowserTake(sessionID: String) {
        guard currentSessionFolder?.id == sessionID, state == .recording || state == .paused else { return }
        pendingBrowserTakeResult = (.stopped, nil)
        if state == .recording { pause() }
    }

    func stopBrowserTake(sessionID: String, status: BrowserTakeMetadata.Status, failureReason: String?) async throws {
        // App owns the shared controller. If its ordinary controls already ended this take,
        // replay cleanup must never stop a different session the user has since started.
        guard currentSessionFolder?.id == sessionID else { return }
        if state == .recording || state == .paused || (state == .stopping && status == .failed) {
            // Keep the on-disk status incomplete until media and action-log finalization both
            // succeed. A crash during teardown must never leave a take labelled finished.
            pendingBrowserTakeResult = (status, failureReason)
        }
        await stop()
        // A source failure may already be finalizing the shared controller. Do not let the
        // engine announce completion while the partial media are still being written.
        while state == .stopping {
            await Task { try? await Task.sleep(for: .milliseconds(20)) }.value
        }
        if browserTakeFinalizationFailed { throw ReplayError.persistenceFailed }
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
                source.onNotice = makeNoticeHandler()
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
        if let folder = completedSession,
           var manifest = RecordingManifest.load(from: folder.manifestURL), manifest.browserTake != nil {
            if !failures.isEmpty {
                manifest.browserTake?.status = .failed
                manifest.browserTake?.failureReason = "captureFailed"
            } else if manifest.browserTake?.status == .recording {
                // Only replay can finish or deliberately stop a browser take. A stop from
                // ordinary recorder controls interrupts orchestration, even if files finalize.
                manifest.browserTake?.status = pendingBrowserTakeResult?.status ?? .failed
                manifest.browserTake?.failureReason = pendingBrowserTakeResult?.failureReason
                    ?? (pendingBrowserTakeResult == nil ? "recordingInterrupted" : nil)
            }
            do {
                try await Task.detached(priority: .utility) {
                    try ActionLog.finalizeJournal(in: folder)
                }.value
                // The replay watchdog can report interruption while media or the journal
                // are being finalized. Do not overwrite that late failure with stopped.
                if manifest.browserTake?.status != .failed, pendingBrowserTakeResult?.status == .failed {
                    manifest.browserTake?.status = .failed
                    manifest.browserTake?.failureReason = pendingBrowserTakeResult?.failureReason
                }
                try manifest.write(to: folder.manifestURL)
            } catch {
                browserTakeFinalizationFailed = true
                manifest.browserTake?.status = .failed
                manifest.browserTake?.failureReason = "persistenceFailed"
                try? manifest.write(to: folder.manifestURL)
                lastError = .writerSetupFailed("Browser take metadata could not be finalized.")
            }
        }
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
        // Replay explicitly paused this take before closing its own Chrome window. The
        // resulting SCStream window-loss notice is expected, not a failed recording.
        // Writer/finalization failures still surface through retire(sources).
        if state == .paused, pendingBrowserTakeResult?.status == .stopped { return }
        lastError = .captureStreamStopped(error.localizedDescription)
        if let folder = currentSessionFolder,
           var manifest = RecordingManifest.load(from: folder.manifestURL), manifest.browserTake != nil {
            manifest.browserTake?.status = .failed
            manifest.browserTake?.failureReason = "captureFailed"
            try? manifest.write(to: folder.manifestURL)
        }
        Task { await stop() }
    }

    private func handleNotice(_ notice: CaptureSourceNotice) {
        // `.starting` included: a source's first buffer can arrive before the controller
        // reaches `.recording`, and that is exactly when the input format is reported.
        guard sessionManager != nil, state != .idle else { return }

        switch notice {
        case let .inputFormat(kind, device, format, time):
            logEvent(.inputFormat, at: time, label: "\(kind.rawValue):\(device):\(format)")

        case let .signalSuspect(kind, device, reason, time):
            logEvent(.signalSuspect, at: time, label: "\(kind.rawValue):\(device):\(reason)")
            // Both causes can fire in one take; one interruption is enough.
            guard signalWarning == nil else { return }
            let error = RecordingError.microphoneSignalSuspect(device: device)
            signalWarning = error.localizedDescription
            lastError = error
            RecordingAlert.post(title: "Microphone audio looks broken", body: error.localizedDescription)
        }
    }

    private func rollbackFailedStart() async {
        for source in sources { source.cancel() }
        allTrackWriters.forEach { $0.cancel() }
        if let folder = currentSessionFolder,
           var manifest = RecordingManifest.load(from: folder.manifestURL), manifest.browserTake != nil {
            manifest.browserTake?.status = .failed
            manifest.browserTake?.failureReason = "startFailed"
            try? manifest.write(to: folder.manifestURL)
        }
        tearDownSessionState()
        applyTransition(.startFailed)
    }

    private func tearDownSessionState() {
        sessionManager?.close()
        sessionManager = nil
        pendingBrowserTakeResult = nil
        sources = []
        activeRequest = nil
        segmentCounts = [:]
        currentTargetName = nil
        currentProfile = nil
        accumulatedPausedDuration = .zero
        pauseStartedAt = nil
        signalWarning = nil
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

    private func makeNoticeHandler() -> @Sendable (CaptureSourceNotice) -> Void {
        { [weak self] notice in
            Task { @MainActor [weak self] in
                self?.handleNotice(notice)
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
