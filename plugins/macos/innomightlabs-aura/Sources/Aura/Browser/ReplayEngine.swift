import Combine
import CoreVideo
import Foundation
import ScreenCaptureKit

/// The real capture boundary: tests need neither Chrome windows nor Screen Recording permission.
@MainActor
protocol ReplayCapturePreparing {
    func prepare(browser: any BrowserDriving, session: BrowserSession, window: WindowSize) async throws -> ReplayCapture
}

struct ReplayCapture {
    var request: RecordingRequest
    var viewport: BrowserViewportMetadata
}

/// A one-shot screenshot, never mutated or reused by a capture stream. Only the calibration
/// worker reads its pixels, under CVPixelBuffer's read lock; no mutable buffer escapes it.
private struct CalibrationFrame: @unchecked Sendable {
    let buffer: CVPixelBuffer
}

@MainActor
struct ChromeReplayCapture: ReplayCapturePreparing {
    func prepare(browser: any BrowserDriving, session: BrowserSession, window: WindowSize) async throws -> ReplayCapture {
        let locator = ChromeWindowLocator()
        let chromeWindow = try await locator.locate(processID: session.chromeProcessID, requestedSize: window)
        let target = CaptureTarget.window(chromeWindow)
        let calibration = try await browser.showCalibrationPage()
        let viewport = try await Self.calibrateWhenPainted {
            let frame = CalibrationFrame(buffer: try await locator.captureFrame(window: chromeWindow, pixelSize: target.pixelSize))
            return try await Task.detached(priority: .userInitiated) {
                try ViewportCalibrator.calibrate(frame.buffer, calibration: calibration)
            }.value
        }
        try Task.checkCancellation()
        return ReplayCapture(
            request: RecordingRequest(profile: RecordingProfile(tracks: [.screen]), screenTarget: target,
                                      hidesSystemCursor: true),
            viewport: viewport
        )
    }

    /// Chrome can acknowledge navigation before the marker page reaches the captured window.
    /// Retry fresh native-size frames, not navigation, and only for the transient paint failure.
    static func calibrateWhenPainted(
        timeout: Duration = .seconds(2), retryDelay: Duration = .milliseconds(100),
        now: () -> ContinuousClock.Instant = { ContinuousClock.now },
        sleep: (Duration) async throws -> Void = { try await Task.sleep(for: $0) },
        attempt: () async throws -> BrowserViewportMetadata
    ) async throws -> BrowserViewportMetadata {
        let deadline = now().advanced(by: timeout)
        while true {
            try Task.checkCancellation()
            do { return try await attempt() }
            catch ViewportCalibrator.CalibrationError.markersNotFound {
                guard now() < deadline else { throw ViewportCalibrator.CalibrationError.markersNotFound }
                try await sleep(min(retryDelay, now().duration(to: deadline)))
                guard now() < deadline else { throw ViewportCalibrator.CalibrationError.markersNotFound }
            }
        }
    }
}

/// Capture hardware and its session clock are the only recording dependencies of replay.
@MainActor
protocol BrowserTakeRecording: AnyObject {
    var state: RecordingState { get }
    var currentSessionFolder: SessionFolder? { get }
    func startBrowserTake(_ request: RecordingRequest, spec: DemoSpec, viewport: BrowserViewportMetadata) async throws -> SessionFolder
    func currentSessionTime() -> TimeInterval?
    func browserStep(label: String)
    func pause()
    func resume()
    func prepareToStopBrowserTake(sessionID: String)
    func stopBrowserTake(sessionID: String, status: BrowserTakeMetadata.Status, failureReason: String?) async throws
}

struct ReplayOptions: Equatable, Sendable {
    /// Bypass the already-signed-in shortcut, not the handover itself. Aura never signs in.
    var forceLoginHandover = false
    /// Rehearsal has real side effects. Let the user reset server-side state before a take.
    var manualResetBeforeTake = false
    var pacing = ActionPacing()
    /// Lines spoken before the take. When present the take is paced to them: each step waits for
    /// its own line to finish, so voice and picture cannot drift apart.
    var narration: NarrationTrack? = nil
}

enum ReplayPhase: String, Equatable, Sendable { case rehearsal, take, reset }

struct ReplayHandover: Equatable, Sendable {
    var phase: ReplayPhase
    var stepID: String?
    var reason: HandoverReason
    var expectationNotMet = false
}

enum ReplayState: Equatable, Sendable {
    case idle, launching, calibrating
    case rehearsing(stepID: String)
    case preparingTake
    case userControl(ReplayHandover)
    case recording(stepID: String?)
    case stopping, finished, stopped
    case failed(reason: String)
}

enum ReplayError: Error, LocalizedError {
    case busy, recorderBusy, expectationFailed, recordingInterrupted, invalidProfile, persistenceFailed
    var errorDescription: String? {
        switch self {
        case .busy: "A browser replay is already running."
        case .recorderBusy: "Stop the current recording before starting a browser take."
        case .expectationFailed: "The browser step did not reach its expected result. Repair the spec before trying again."
        case .recordingInterrupted: "The browser recording was interrupted. Any partial session has been retained."
        case .invalidProfile: "Choose a local browser profile directory. Credentials are entered only in Chrome."
        case .persistenceFailed: "The browser take's session data could not be saved. Any partial session has been retained."
        }
    }
}

/// Only fixed local descriptions and exact machine-code matches may reach replay diagnostics.
/// Associated strings and arbitrary underlying errors can contain page content or credentials.
func replayFailureDescription(_ error: any Error) -> String {
    switch error {
    case let error as ViewportCalibrator.CalibrationError:
        return error.localizedDescription
    case let error as ChromeWindowLocator.LocatorError:
        return error.localizedDescription
    case ReplayError.recordingInterrupted:
        return "The browser recording was interrupted."
    case ReplayError.persistenceFailed:
        return "The browser take's session data could not be saved."
    case let error as ReplayError:
        return error.localizedDescription
    case is DemoSpecError:
        return "The demo spec is invalid. Check its actions, parameters and allowed origins before trying again."
    case BrowserHostError.refused(let code):
        switch code {
        case "elementNotFound":
            return "The target element was not found (elementNotFound). Check the step's locator and that the page is ready."
        case "ambiguousLocator":
            return "More than one element matches the locator (ambiguousLocator). Make the step's locator more specific."
        case "sensitiveInput":
            return "Aura refused a sensitive input (sensitiveInput). Use a manual handover to enter credentials in Chrome."
        case "originRefused":
            return "Navigation was refused (originRefused). Check the spec's allowed origins; use a handover for sign-in."
        case "invalidLocator":
            return "The locator is invalid (invalidLocator). Repair the step's locator before trying again."
        case "framesUnsupported":
            return "Frame targets are unsupported (framesUnsupported). Choose an element in the main page."
        case "notReady":
            return "Chrome is not ready for automation (notReady). Finish the manual handover on an approved origin."
        case "userControl", "userControlRequired":
            return "The command requires a different browser control mode. Check the spec's manual handovers."
        default:
            return "The browser refused the command. Check the spec and try again."
        }
    case let error as BrowserHostError:
        return error.localizedDescription
    default:
        return "Browser replay failed. Check the spec and try again."
    }
}

/// No UI or review-window ownership. App supplies its shared recording controller and owns
/// this engine's window. A successful rehearsal is mandatory for every start, including retakes.
@MainActor
final class ReplayEngine: ObservableObject {
    @Published private(set) var state: ReplayState = .idle
    @Published private(set) var sessionFolder: SessionFolder?
    @Published private(set) var lastError: String?
    @Published private(set) var failedStepID: String?
    var isRunning: Bool { runTask != nil }

    private let browser: any BrowserDriving
    private let recorder: any BrowserTakeRecording
    private let capture: any ReplayCapturePreparing
    private var runTask: Task<Void, Never>?
    private var eventTask: Task<Void, Never>?
    private var recorderMonitor: Task<Void, Never>?
    private var interruptionTask: Task<Void, Never>?
    private var expectedRecorderState: RecordingState = .recording
    private var log: ActionLogWriter?
    private var currentStepID: String?
    private var takeStarted = false
    private var resumeRequested = false
    private var failureReason: String?
    private var calibratedViewport: BrowserViewportMetrics?
    private var narrationLines: [NarrationLine] = []

    init(browser: any BrowserDriving, recordingController: RecordingController) {
        self.browser = browser
        recorder = recordingController
        capture = ChromeReplayCapture()
    }

    init(browser: any BrowserDriving, recorder: any BrowserTakeRecording, capture: any ReplayCapturePreparing) {
        self.browser = browser; self.recorder = recorder; self.capture = capture
    }

    /// Returns immediately; observe `state`. The caller has explicitly approved rehearsal's
    /// real side effects. No credentials are accepted, fetched or stored by this API.
    func start(spec: DemoSpec, profileDirectory: URL, options: ReplayOptions = ReplayOptions()) throws {
        guard runTask == nil else { throw ReplayError.busy }
        guard recorder.state == .idle else { throw ReplayError.recorderBusy }
        try spec.validate()
        guard profileDirectory.isFileURL else { throw ReplayError.invalidProfile }
        guard options.pacing.moveSeconds.isFinite, (0...10).contains(options.pacing.moveSeconds),
              (1...240).contains(options.pacing.steps), (0...1000).contains(options.pacing.typeDelayMs) else {
            throw DemoSpecError.invalid("Invalid replay pacing")
        }
        sessionFolder = nil; lastError = nil; failedStepID = nil; failureReason = nil
        takeStarted = false; currentStepID = nil; resumeRequested = false; calibratedViewport = nil
        narrationLines = []
        state = .launching
        runTask = Task { await self.run(spec: spec, profileDirectory: profileDirectory, options: options) }
    }

    /// The only way out of manual control. A failed doneWhen keeps control with the user;
    /// nothing types credentials or polls page content while the user is signing in.
    func resume() {
        guard case .userControl = state else { return }
        resumeRequested = true
    }

    /// Safe in every state, including launch, calibration, rehearsal, handover and start-up.
    /// Closing the host also interrupts a command that is waiting on the page.
    func stop() async {
        guard let task = runTask else { return }
        // Finalization already owns teardown. In particular, Stop must not close Chrome
        // underneath a successful take whose capture stream is still being retired.
        if state == .stopping {
            await task.value
            return
        }
        if takeStarted, ownsRecording, let folder = sessionFolder {
            expectedRecorderState = .paused
            recorder.prepareToStopBrowserTake(sessionID: folder.id)
        }
        state = .stopping
        task.cancel()
        await browser.close()
        await task.value
    }

    func waitUntilFinished() async { await runTask?.value }

    deinit { eventTask?.cancel() }

    private func run(spec: DemoSpec, profileDirectory: URL, options: ReplayOptions) async {
        // Cancelling an AsyncStream iterator terminates the host's stream permanently. Keep
        // one weak observer for this engine's lifetime so a retake still receives safety events.
        if eventTask == nil {
            eventTask = Task { [weak self, browser] in
                for await event in browser.events {
                    guard !Task.isCancelled else { break }
                    self?.receive(event)
                }
            }
        }
        var terminal: ReplayState = .finished
        do {
            try Task.checkCancellation()
            let session = try await browser.launch(BrowserLaunch(profileDirectory: profileDirectory,
                startURL: spec.startURL, window: spec.window, allowedOrigins: spec.allowedOrigins))
            try Task.checkCancellation()
            state = .calibrating
            let prepared = try await capture.prepare(browser: browser, session: session, window: spec.window)
            try Task.checkCancellation()
            calibratedViewport = prepared.viewport.viewport
            let firstRecordedStep = spec.steps.prefix { step in
                if case .handover = step.action { true } else { false }
            }.count
            try await prepareStart(spec: spec, phase: .rehearsal, options: options, leadingCount: firstRecordedStep)
            for step in spec.steps.dropFirst(firstRecordedStep) {
                try Task.checkCancellation()
                state = .rehearsing(stepID: step.id)
                try await perform(step, spec: spec, phase: .rehearsal, options: options)
            }

            state = .preparingTake
            if options.manualResetBeforeTake {
                try await handover(reason: .manual, doneWhen: nil, stepID: nil, phase: .reset,
                                   force: true, navigation: spec.startURL)
            }
            // A declared leading handover grants user control before the first site request,
            // including redirects to external identity providers. Never navigate there first.
            try await prepareStart(spec: spec, phase: .take, options: options, leadingCount: firstRecordedStep)
            try Task.checkCancellation()
            state = .preparingTake
            let metrics = try await browser.viewportMetrics()
            guard metrics == calibratedViewport else {
                failureReason = "viewportResized"
                throw ReplayError.recordingInterrupted
            }
            var request = prepared.request
            request.hidesSystemCursor = true
            request.browserTake = BrowserTakeMetadata(specID: spec.id, revision: spec.revision)
            takeStarted = true
            sessionFolder = try await recorder.startBrowserTake(request, spec: spec, viewport: prepared.viewport)
            try Task.checkCancellation()
            guard let sessionFolder else { throw ReplayError.recordingInterrupted }
            expectedRecorderState = .recording
            startRecorderMonitor()
            log = try ActionLogWriter(folder: sessionFolder)
            state = .recording(stepID: nil)
            try await speakEdge(.intro, options: options)
            for step in spec.steps.dropFirst(firstRecordedStep) {
                try Task.checkCancellation()
                guard ownsRecording, recorder.state == .recording else { throw ReplayError.recordingInterrupted }
                state = .recording(stepID: step.id)
                try await perform(step, spec: spec, phase: .take, options: options)
            }
            try await speakEdge(.outro, options: options)
            try Task.checkCancellation()
            guard ownsRecording, recorder.state == .recording else { throw ReplayError.recordingInterrupted }
        } catch {
            let failedPhase = failurePhase
            if failureReason != nil || (!Task.isCancelled && !(error is CancellationError)) {
                switch state {
                case .rehearsing(let id): failedStepID = id
                case .recording(let id): failedStepID = id
                case .userControl(let handover): failedStepID = handover.stepID
                default: failedStepID = currentStepID
                }
            }
            if let failureReason {
                terminal = .failed(reason: failureReason)
                lastError = "\(failedPhase): \(message(for: failureReason))"
            } else if Task.isCancelled || error is CancellationError {
                terminal = .stopped
            } else {
                let reason = error is ReplayError ? "replayFailed" : "browserFailed"
                terminal = .failed(reason: reason)
                lastError = "\(failedPhase): \(replayFailureDescription(error))\(partialTakeDescription)"
            }
        }
        let closeAfterRecording = terminal == .finished
        state = .stopping
        currentStepID = nil
        recorderMonitor?.cancel(); recorderMonitor = nil
        await interruptionTask?.value
        interruptionTask = nil
        // Failure/Stop must interrupt an in-flight command. A successful take has no
        // command to interrupt: its captured window must outlive media finalization.
        if !closeAfterRecording { await browser.close() }
        log?.close(); log = nil
        if takeStarted, let folder = sessionFolder, !narrationLines.isEmpty {
            // Kept for partial takes too: a line already played is already in the picture's timeline.
            try? JSONEncoder().encode(narrationLines).write(to: folder.narrationLinesURL, options: .atomic)
        }
        if takeStarted, let folder = sessionFolder {
            let status: BrowserTakeMetadata.Status
            switch terminal {
            case .finished: status = .finished
            case .stopped: status = .stopped
            default: status = .failed
            }
            do {
                try await recorder.stopBrowserTake(sessionID: folder.id, status: status, failureReason: status == .failed ? (failureReason ?? "replayFailed") : nil)
                // Ordinary App controls may already have finalized this folder. Preserve its
                // media, but do not label an interrupted replay as a successful manual stop.
                if status == .failed, var manifest = RecordingManifest.load(from: folder.manifestURL),
                   manifest.browserTake != nil, manifest.browserTake?.status != .failed {
                    manifest.browserTake?.status = .failed
                    manifest.browserTake?.failureReason = failureReason ?? "replayFailed"
                    try manifest.write(to: folder.manifestURL)
                }
                if status != .failed, let folder = sessionFolder,
                   RecordingManifest.load(from: folder.manifestURL)?.browserTake?.status == .failed {
                    terminal = .failed(reason: "recordingFailed")
                    lastError = "Finalizing recording: \(message(for: "recordingFailed"))"
                }
            } catch {
                terminal = .failed(reason: "persistenceFailed")
                lastError = "Finalizing recording: \(message(for: "persistenceFailed"))"
            }
        }
        if closeAfterRecording { await browser.close() }
        takeStarted = false
        state = terminal
        runTask = nil
    }

    private var ownsRecording: Bool {
        guard let sessionFolder else { return false }
        return recorder.currentSessionFolder?.id == sessionFolder.id
    }

    private func prepareStart(spec: DemoSpec, phase: ReplayPhase, options: ReplayOptions, leadingCount: Int) async throws {
        try Task.checkCancellation()
        if leadingCount == 0 {
            _ = try await browser.perform(.goto(spec.startURL), pacing: .rehearsal)
            return
        }
        for (index, step) in spec.steps.prefix(leadingCount).enumerated() {
            try Task.checkCancellation()
            state = phase == .rehearsal ? .rehearsing(stepID: step.id) : .preparingTake
            try await perform(step, spec: spec, phase: phase, options: options,
                              handoverNavigation: index == 0 ? spec.startURL : nil)
        }
    }

    private func startRecorderMonitor() {
        recorderMonitor = Task { [weak self] in
            while !Task.isCancelled {
                guard let self, self.state != .stopping else { return }
                guard self.ownsRecording, self.recorder.state == self.expectedRecorderState else {
                    self.fail("recordingInterrupted")
                    return
                }
                do { try await Task.sleep(for: .milliseconds(20)) }
                catch { return }
            }
        }
    }

    private func perform(_ step: DemoStep, spec: DemoSpec, phase: ReplayPhase, options: ReplayOptions,
                         handoverNavigation: URL? = nil) async throws {
        if case .handover(let reason, let doneWhen) = step.action {
            try await handover(reason: reason, doneWhen: doneWhen, stepID: step.id, phase: phase,
                               force: reason == .login && options.forceLoginHandover, navigation: handoverNavigation)
            if let expect = step.expect, !(try await browser.check(expect, timeout: 10)) {
                throw ReplayError.expectationFailed
            }
        } else {
            var line: PlayingLine?
            if phase == .take {
                currentStepID = step.id
                recorder.browserStep(label: step.intent)
                try append(.stepStart)
                line = try beginLine(.step(step.id), options: options, stepID: step.id)
                // The viewer hears what is about to happen, then sees it.
                if line != nil { try await wait(NarrationTiming.actionLead) }
            }
            let outcome = try await browser.perform(try step.action.resolved(parameters: spec.parameters),
                                                    pacing: phase == .rehearsal ? .rehearsal : options.pacing)
            try Task.checkCancellation()
            if phase == .take {
                if outcome.viewport != calibratedViewport {
                    failureReason = "viewportResized"
                    throw ReplayError.recordingInterrupted
                }
                if case .fill = step.action { try append(.typed) }
                if let expect = step.expect, !(try await browser.check(expect, timeout: 10)) {
                    throw ReplayError.expectationFailed
                }
                let rect = outcome.rect.map { CGRect(x: $0.x, y: $0.y, width: $0.width, height: $0.height) }
                try append(.stepEnd, rect: rect)
                try await finish(line, options: options)
                currentStepID = nil
            } else if let expect = step.expect, !(try await browser.check(expect, timeout: 10)) {
                throw ReplayError.expectationFailed
            }
        }
        try Task.checkCancellation()
    }

    // MARK: - Narration

    /// A line that has started playing: when, and how long it runs.
    private struct PlayingLine {
        let clip: NarrationClip
        let startedAt: TimeInterval
    }

    /// Notes that a line starts now and puts its clip beside the session, where the review window
    /// looks for it. Nil when the take has no line for this slot.
    private func beginLine(_ slot: NarrationSlot, options: ReplayOptions, stepID: String?) throws -> PlayingLine? {
        guard let clip = options.narration?.clips[slot], ownsRecording, let folder = sessionFolder,
              let at = recorder.currentSessionTime() else { return nil }
        let line = NarrationLine(at: at, text: clip.text, duration: clip.duration, stepID: stepID)
        try FileManager.default.createDirectory(at: folder.narrationURL, withIntermediateDirectories: true)
        try FileManager.default.copyItem(at: clip.url, to: folder.narrationClipURL(for: line.id))
        narrationLines.append(line)
        return PlayingLine(clip: clip, startedAt: at)
    }

    /// Waits out whatever is left of the line, then the settling gap. Without narration a step
    /// ends as soon as its action does, as it always has.
    private func finish(_ line: PlayingLine?, options: ReplayOptions) async throws {
        guard options.narration != nil else { return }
        if let line, let now = recorder.currentSessionTime() {
            try await wait(NarrationTiming.remainingHold(clip: line.clip.duration, elapsed: now - line.startedAt))
        }
        try await wait(NarrationTiming.gap)
    }

    /// The intro and outro: a quiet beat at the edge of the video, the line, and another beat.
    private func speakEdge(_ slot: NarrationSlot, options: ReplayOptions) async throws {
        guard options.narration != nil else { return }
        if slot == .intro { try await wait(NarrationTiming.edgeHold) }
        if let line = try beginLine(slot, options: options, stepID: nil) {
            try await wait(line.clip.duration)
        }
        if slot == .outro { try await wait(NarrationTiming.edgeHold) } else { try await wait(NarrationTiming.gap) }
    }

    private func wait(_ seconds: TimeInterval) async throws {
        guard seconds > 0 else { return }
        try await Task.sleep(for: .seconds(seconds))
    }

    private func handover(reason: HandoverReason, doneWhen: Expectation?, stepID: String?, phase: ReplayPhase,
                          force: Bool, navigation: URL? = nil) async throws {
        if navigation == nil, !force, let doneWhen, try await browser.check(doneWhen, timeout: 0) { return }
        let wasRecording = takeStarted && ownsRecording && recorder.state == .recording
        if wasRecording {
            expectedRecorderState = .paused
            recorder.pause()
        }
        currentStepID = nil
        resumeRequested = false
        state = .userControl(ReplayHandover(phase: phase, stepID: stepID, reason: reason))
        try await browser.setUserControl(true)
        try Task.checkCancellation()
        var controlReturned = false
        if let navigation {
            try await browser.navigateForHandover(to: navigation)
            try Task.checkCancellation()
            // Starting on a blank page means doneWhen cannot be checked before navigation.
            // Try the authenticated shortcut only after granting control and loading the site.
            if !force, let doneWhen {
                controlReturned = try await returnControl(doneWhen: doneWhen, timeout: 0)
            }
        }
        while !controlReturned {
            while !resumeRequested { try await Task.sleep(for: .milliseconds(50)) }
            try Task.checkCancellation()
            resumeRequested = false
            controlReturned = try await returnControl(doneWhen: doneWhen, timeout: 10)
            if controlReturned { break }
            state = .userControl(ReplayHandover(phase: phase, stepID: stepID, reason: reason, expectationNotMet: true))
        }
        try Task.checkCancellation()
        if wasRecording {
            guard ownsRecording, recorder.state == .paused else { throw ReplayError.recordingInterrupted }
            expectedRecorderState = .recording
            recorder.resume()
        }
        switch phase {
        case .rehearsal: state = .rehearsing(stepID: stepID ?? "")
        case .take: state = takeStarted ? .recording(stepID: stepID) : .preparingTake
        case .reset: state = .preparingTake
        }
    }

    /// notReady means the user is still on an external login origin. The host keeps its
    /// privacy/routing handover active; only another explicit Resume may try to leave it.
    private func returnControl(doneWhen: Expectation?, timeout: TimeInterval) async throws -> Bool {
        do { try await browser.setUserControl(false) }
        catch BrowserHostError.refused("notReady") { return false }
        try Task.checkCancellation()
        if let doneWhen, !(try await browser.check(doneWhen, timeout: timeout)) {
            try await browser.setUserControl(true)
            try Task.checkCancellation()
            return false
        }
        return true
    }

    private func append(_ kind: ActionLog.Entry.Kind, point: CGPoint? = nil, rect: CGRect? = nil) throws {
        guard ownsRecording, let stepID = currentStepID, let t = recorder.currentSessionTime(), recorder.state == .recording else { return }
        try log?.append(ActionLog.Entry(t: t, stepID: stepID, kind: kind, point: point, rect: rect))
    }

    private func receive(_ event: BrowserEvent) {
        guard runTask != nil, state != .stopping else { return }
        // Launch reports its own failures. A close event still queued from the preceding take
        // must not cancel the next launch on the same host.
        if state == .launching, case .closed = event { return }
        switch event {
        case .viewportResized where takeStarted: fail("viewportResized")
        case .navigationRefused: fail("navigationRefused")
        case .closed: fail("browserClosed")
        default: break
        }
        guard case .recording = state else { return }
        do {
            switch event {
            case .mouseMoved(let point): try append(.mouseMove, point: point)
            case .mouseDown(let point): try append(.mouseDown, point: point)
            case .mouseUp(let point): try append(.mouseUp, point: point)
            default: break
            }
        } catch { fail("persistenceFailed") }
    }

    private func fail(_ reason: String) {
        guard failureReason == nil else { return }
        failureReason = reason
        runTask?.cancel()
        interruptionTask = Task { [browser] in await browser.close() }
    }

    private var failurePhase: String {
        switch state {
        case .launching: "Launching Chrome"
        case .calibrating: "Viewport calibration"
        case .rehearsing: "Rehearsal"
        case .preparingTake: "Preparing take"
        case .userControl(let handover): "User control (\(handover.phase.rawValue))"
        case .recording: "Recording take"
        case .stopping: "Finalizing recording"
        default: "Browser replay"
        }
    }

    private var partialTakeDescription: String {
        sessionFolder == nil ? "" : " The partial take has been retained."
    }

    private func message(for reason: String) -> String {
        let description: String
        switch reason {
        case "viewportResized": description = "The Chrome viewport changed size. Start a new take."
        case "navigationRefused": description = "Chrome refused navigation outside the approved origins."
        case "browserClosed": description = "The browser closed before replay finished."
        case "recordingInterrupted": description = replayFailureDescription(ReplayError.recordingInterrupted)
        case "persistenceFailed": description = replayFailureDescription(ReplayError.persistenceFailed)
        default: description = "Browser replay failed. Check the spec and try again."
        }
        return description + partialTakeDescription
    }
}
