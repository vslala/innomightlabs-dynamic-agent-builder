import XCTest
@testable import Aura

@MainActor
final class ReplayEngineTests: XCTestCase {
    private let url = URL(string: "https://example.com")!

    private func spec(_ actions: [DemoAction] = [.wait(seconds: 0)]) -> DemoSpec {
        DemoSpec(title: "Demo", startURL: url, allowedOrigins: ["https://example.com"],
                 window: WindowSize(width: 1200, height: 800),
                 steps: actions.enumerated().map { DemoStep(id: "s\($0.offset)", action: $0.element, intent: "Step \($0.offset)") })
    }

    private func fixture() throws -> (ReplayEngine, FakeReplayBrowser, FakeReplayRecorder, FakeReplayCapture) {
        let browser = FakeReplayBrowser()
        let recorder = try FakeReplayRecorder()
        let capture = FakeReplayCapture()
        let engine = ReplayEngine(browser: browser, recorder: recorder, capture: capture)
        return (engine, browser, recorder, capture)
    }

    private func waitFor(_ predicate: () -> Bool) async throws {
        for _ in 0..<1000 {
            if predicate() { return }
            try await Task.sleep(for: .milliseconds(2))
        }
        XCTFail("Replay did not reach the expected state")
        throw ReplayError.recordingInterrupted
    }

    func testRehearsesThenReturnsToStartAndPersistsExactSpecAndSessionTimes() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        let target = ElementTarget(candidates: [.init(testId: "name")])
        let demo = spec([.fill(target, value: .parameter("site")), .click(target)])
        var input = demo
        input.parameters = ["site": "public value"]
        browser.onPerform = { _, pacing in
            if pacing != .rehearsal {
                recorder.time += 0.25
                browser.emit(.mouseMoved(to: CGPoint(x: 8, y: 9)))
                await Task.yield()
            }
        }
        try engine.start(spec: input, profileDirectory: recorder.folder.rootURL)
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.state, .finished)
        XCTAssertEqual(browser.actions.count, 6) // start, two rehearsal actions, reset, two take actions
        XCTAssertEqual(browser.actions.prefix(4).map(\.1), Array(repeating: .rehearsal, count: 4))
        XCTAssertEqual(browser.actions[3].0, .goto(url))
        XCTAssertTrue(recorder.request?.hidesSystemCursor == true)
        XCTAssertEqual(recorder.request?.profile.tracks, [.screen])
        XCTAssertEqual(try JSONDecoder().decode(DemoSpec.self, from: Data(contentsOf: recorder.folder.demoSpecURL)), input)
        XCTAssertEqual(try JSONDecoder().decode(BrowserViewportMetadata.self, from: Data(contentsOf: recorder.folder.viewportURL)), FakeReplayCapture.viewport)
        let log = try JSONDecoder().decode(ActionLog.self, from: Data(contentsOf: recorder.folder.actionLogURL))
        XCTAssertEqual(log.entries.filter { $0.kind == .stepStart }.map(\.t), [0, 0.25])
        XCTAssertEqual(log.entries.filter { $0.kind == .stepEnd }.map(\.t), [0.25, 0.5])
        XCTAssertEqual(log.entries.filter { $0.kind == .typed }.count, 1)
        XCTAssertTrue(log.entries.contains { $0.kind == .mouseMove })
        XCTAssertEqual(recorder.markers, ["Step 0", "Step 1"])
        XCTAssertEqual(recorder.completedCount, 1)
        XCTAssertEqual(RecordingManifest.load(from: recorder.folder.manifestURL)?.browserTake?.status, .finished)
        XCTAssertFalse(try String(contentsOf: recorder.folder.actionLogURL, encoding: .utf8).contains("public value"))
    }

    func testSuccessfulTakeFinalizesMediaAndActionLogBeforeClosingChrome() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        var lifecycle: [String] = []
        recorder.onFinalize = {
            lifecycle.append("finalize")
            XCTAssertEqual(browser.closeCount, 0)
        }
        recorder.onCompleted = { lifecycle.append("completed") }
        browser.onClose = {
            lifecycle.append("close")
            XCTAssertEqual(recorder.state, .idle)
            XCTAssertEqual(recorder.completedCount, 1)
            XCTAssertEqual(RecordingManifest.load(from: recorder.folder.manifestURL)?.browserTake?.status, .finished)
            XCTAssertTrue(FileManager.default.fileExists(atPath: recorder.folder.actionLogURL.path))
        }
        try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
        await engine.waitUntilFinished()
        XCTAssertEqual(lifecycle, ["finalize", "completed", "close"])
        XCTAssertEqual(engine.state, .finished)
        XCTAssertEqual(browser.closeCount, 1)
    }

    func testStopDuringSuccessfulFinalizationDoesNotCloseWindowEarly() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        var releaseFinalization: CheckedContinuation<Void, Never>?
        recorder.onFinalize = {
            await withCheckedContinuation { releaseFinalization = $0 }
        }
        try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
        try await waitFor { releaseFinalization != nil }
        XCTAssertEqual(engine.state, .stopping)
        let stop = Task { await engine.stop() }
        await Task.yield()
        XCTAssertEqual(browser.closeCount, 0)
        XCTAssertEqual(recorder.state, .stopping)
        releaseFinalization?.resume()
        await stop.value
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.state, .finished)
        XCTAssertEqual(browser.closeCount, 1)
        XCTAssertEqual(RecordingManifest.load(from: recorder.folder.manifestURL)?.browserTake?.status, .finished)
    }

    func testUserStopPausesBeforeCommandInterruptionAndRetainsStoppedPartial() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        var lifecycle: [String] = []
        recorder.onPause = { lifecycle.append("pause") }
        recorder.onFinalize = { lifecycle.append("finalize") }
        browser.onPerform = { _, pacing in
            guard pacing != .rehearsal else { return }
            // Models a host command released only by closing Chrome, not task cancellation.
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                browser.onClose = {
                    lifecycle.append("close")
                    XCTAssertEqual(recorder.state, .paused)
                    XCTAssertTrue(recorder.expectsWindowClose)
                    recorder.windowClosed()
                    continuation.resume(throwing: BrowserHostError.terminated)
                }
            }
        }
        try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
        try await waitFor { browser.onClose != nil }
        await engine.stop()
        XCTAssertEqual(lifecycle, ["pause", "close", "finalize"])
        XCTAssertEqual(engine.state, .stopped)
        XCTAssertEqual(recorder.pauses, 1)
        XCTAssertEqual(recorder.completedCount, 1)
        let manifest = RecordingManifest.load(from: recorder.folder.manifestURL)
        XCTAssertEqual(manifest?.browserTake?.status, .stopped)
        XCTAssertNil(manifest?.browserTake?.failureReason)
        XCTAssertTrue(FileManager.default.fileExists(atPath: recorder.folder.actionLogURL.path))
    }

    func testFailedTakeInterruptsBeforeFinalizationAndRetainsFailedPartial() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        var lifecycle: [String] = []
        recorder.onFinalize = { lifecycle.append("finalize") }
        browser.onPerform = { _, pacing in
            guard pacing != .rehearsal else { return }
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                browser.onClose = {
                    lifecycle.append("close")
                    recorder.windowClosed()
                    continuation.resume(throwing: BrowserHostError.terminated)
                }
                browser.emit(.navigationRefused(URL(string: "https://refused.example")!))
            }
        }
        try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
        await engine.waitUntilFinished()
        XCTAssertEqual(lifecycle, ["close", "finalize"])
        XCTAssertEqual(engine.state, .failed(reason: "navigationRefused"))
        XCTAssertFalse(recorder.expectsWindowClose)
        XCTAssertEqual(recorder.completedCount, 1)
        XCTAssertEqual(RecordingManifest.load(from: recorder.folder.manifestURL)?.browserTake?.status, .failed)
        XCTAssertTrue(FileManager.default.fileExists(atPath: recorder.folder.actionLogURL.path))
    }

    func testFinalizationErrorStillClosesChrome() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        var lifecycle: [String] = []
        recorder.onFinalize = {
            lifecycle.append("finalize")
            throw ReplayError.persistenceFailed
        }
        browser.onClose = { lifecycle.append("close") }
        try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
        await engine.waitUntilFinished()
        XCTAssertEqual(lifecycle, ["finalize", "close"])
        XCTAssertEqual(engine.state, .failed(reason: "persistenceFailed"))
        XCTAssertEqual(browser.closeCount, 1)
    }

    func testInvalidSpecNeverLaunches() throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        var invalid = spec(); invalid.allowedOrigins = []
        XCTAssertThrowsError(try engine.start(spec: invalid, profileDirectory: recorder.folder.rootURL))
        XCTAssertEqual(browser.launchCount, 0)
        XCTAssertEqual(engine.state, .idle)
    }

    func testCalibrationFailureNamesViewportCalibrationWithoutStartingRehearsalOrSession() async throws {
        let (engine, browser, recorder, capture) = try fixture()
        defer { recorder.removeFiles() }
        capture.failure = ViewportCalibrator.CalibrationError.markersNotFound
        try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.state, .failed(reason: "browserFailed"))
        XCTAssertEqual(engine.lastError, "Viewport calibration: " + ViewportCalibrator.CalibrationError.markersNotFound.localizedDescription)
        XCTAssertTrue(browser.actions.isEmpty)
        XCTAssertEqual(browser.closeCount, 1)
        XCTAssertEqual(recorder.starts, 0)
        XCTAssertEqual(recorder.completedCount, 0)
        XCTAssertNil(recorder.currentSessionFolder)
        XCTAssertNil(engine.sessionFolder)
        XCTAssertNil(engine.failedStepID)
        XCTAssertFalse(engine.lastError?.contains("retained") ?? true)
    }

    func testWindowLocatorFailuresKeepTrustedDetailsAndCalibrationPhase() async throws {
        let errors: [ChromeWindowLocator.LocatorError] = [.invalidRequest, .notFound, .ambiguous, .captureUnavailable, .missingFrame]
        for error in errors {
            let (engine, browser, recorder, capture) = try fixture()
            defer { recorder.removeFiles() }
            capture.failure = error
            try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
            await engine.waitUntilFinished()
            XCTAssertEqual(engine.lastError, "Viewport calibration: " + error.localizedDescription)
            XCTAssertTrue(browser.actions.isEmpty)
            XCTAssertEqual(recorder.starts, 0)
            XCTAssertNil(engine.sessionFolder)
        }
    }

    func testHostLocatorAmbiguityIdentifiesRehearsalAndFailedStepSafely() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        let target = ElementTarget(candidates: [.init(testId: "private-page-secret")])
        browser.onPerform = { action, _ in
            if case .click = action { throw BrowserHostError.refused("ambiguousLocator") }
        }
        try engine.start(spec: spec([.click(target)]), profileDirectory: recorder.folder.rootURL)
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.state, .failed(reason: "browserFailed"))
        XCTAssertEqual(engine.failedStepID, "s0")
        let description = try XCTUnwrap(engine.lastError)
        XCTAssertTrue(description.hasPrefix("Rehearsal: "))
        XCTAssertTrue(description.contains("ambiguousLocator"))
        XCTAssertTrue(description.contains("more specific"))
        XCTAssertFalse(description.contains("private-page-secret"))
        XCTAssertFalse(description.contains("retained"))
        XCTAssertEqual(recorder.starts, 0)
    }

    func testUntrustedErrorsAndUnknownRefusalCodesNeverExposeAssociatedValues() async throws {
        let secret = "page-secret=https://private.example/?token=hidden"
        let errors: [any Error] = [
            BrowserHostError.refused(secret),
            BrowserHostError.refused("ambiguousLocator " + secret),
            DemoSpecError.invalid(secret),
            NSError(domain: secret, code: 1, userInfo: [NSLocalizedDescriptionKey: secret])
        ]
        for error in errors {
            let (engine, _, recorder, capture) = try fixture()
            defer { recorder.removeFiles() }
            capture.failure = error
            try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
            await engine.waitUntilFinished()
            let description = try XCTUnwrap(engine.lastError)
            XCTAssertTrue(description.hasPrefix("Viewport calibration: "))
            XCTAssertFalse(description.contains(secret))
            XCTAssertFalse(description.contains("ambiguousLocator"))
            XCTAssertFalse(description.contains("retained"))
        }
        XCTAssertEqual(replayFailureDescription(BrowserHostError.refused(secret)),
                       "The browser refused the command. Check the spec and try again.")
    }

    func testKnownHostCodesHaveFixedActionableDescriptions() {
        let codes = ["elementNotFound", "ambiguousLocator", "sensitiveInput", "originRefused", "invalidLocator", "framesUnsupported", "notReady"]
        for code in codes {
            let description = replayFailureDescription(BrowserHostError.refused(code))
            XCTAssertTrue(description.contains("(\(code))"), code)
            XCTAssertGreaterThan(description.count, code.count + 40, code)
        }
        XCTAssertEqual(replayFailureDescription(BrowserHostError.timedOut), BrowserHostError.timedOut.localizedDescription)
        XCTAssertEqual(replayFailureDescription(ReplayError.expectationFailed), ReplayError.expectationFailed.localizedDescription)
    }

    func testRecordingFailureIncludesPhaseStepAndRetainedPartialOnlyAfterSessionStarts() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        browser.onPerform = { _, pacing in
            if pacing != .rehearsal { throw ReplayError.recordingInterrupted }
        }
        try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.state, .failed(reason: "replayFailed"))
        XCTAssertEqual(engine.failedStepID, "s0")
        XCTAssertNotNil(engine.sessionFolder)
        XCTAssertEqual(engine.lastError, "Recording take: The browser recording was interrupted. The partial take has been retained.")
        XCTAssertEqual(recorder.completedCount, 1)
    }

    func testPreSessionInterruptionDoesNotClaimRetainedPartial() async throws {
        let (engine, _, recorder, capture) = try fixture()
        defer { recorder.removeFiles() }
        capture.failure = ReplayError.recordingInterrupted
        try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.lastError, "Viewport calibration: The browser recording was interrupted.")
        XCTAssertNil(engine.sessionFolder)
        XCTAssertEqual(recorder.starts, 0)
    }

    func testFailedRehearsalNeverStartsRecording() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        browser.checkResult = false
        var input = spec(); input.steps[0].expect = Expectation(url: "/ready")
        try engine.start(spec: input, profileDirectory: recorder.folder.rootURL)
        await engine.waitUntilFinished()
        guard case .failed = engine.state else { return XCTFail("Rehearsal must fail") }
        XCTAssertEqual(engine.failedStepID, input.steps[0].id)
        XCTAssertEqual(recorder.starts, 0)
        XCTAssertEqual(browser.closeCount, 1)
    }

    func testAlreadySignedInSkipsHandoverUnlessForced() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        let input = spec([.handover(reason: .login, doneWhen: Expectation(url: "/ready")), .wait(seconds: 0)])
        try engine.start(spec: input, profileDirectory: recorder.folder.rootURL)
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.state, .finished)
        XCTAssertEqual(browser.controlChanges, [true, false, true, false])
        XCTAssertEqual(browser.handoverNavigations, [url, url])
        browser.controlChanges = []
        browser.handoverNavigations = []

        try engine.start(spec: input, profileDirectory: recorder.folder.rootURL,
                         options: ReplayOptions(forceLoginHandover: true))
        try await waitFor { if case .userControl = engine.state { true } else { false } }
        XCTAssertEqual(recorder.starts, 1) // first take only
        let commandCount = browser.commandCount
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertEqual(browser.commandCount, commandCount) // no credential polling
        engine.resume()
        try await waitFor {
            if case .userControl(let handover) = engine.state { handover.phase == .take } else { false }
        }
        XCTAssertEqual(recorder.starts, 1) // leading handover is still before capture
        engine.resume()
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.state, .finished)
        XCTAssertEqual(browser.controlChanges, [true, false, true, false])
        XCTAssertEqual(browser.handoverNavigations, [url, url])
    }

    func testMidTakeHandoverPausesAndNeedsManualResume() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        browser.checkResult = false
        let input = spec([.wait(seconds: 0), .handover(reason: .login, doneWhen: Expectation(url: "/ready")), .wait(seconds: 0)])
        try engine.start(spec: input, profileDirectory: recorder.folder.rootURL,
                         options: ReplayOptions(forceLoginHandover: true))
        try await waitFor { if case .userControl = engine.state { true } else { false } }
        browser.checkResult = true
        engine.resume()
        try await waitFor {
            if case .userControl(let handover) = engine.state { handover.phase == .take } else { false }
        }
        XCTAssertEqual(recorder.state, .paused)
        XCTAssertEqual(recorder.pauses, 1)
        XCTAssertEqual(recorder.currentSessionTime(), 0)
        let commandCount = browser.commandCount
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertEqual(browser.commandCount, commandCount)
        browser.checkResult = false
        engine.resume()
        try await waitFor {
            if case .userControl(let handover) = engine.state { handover.expectationNotMet } else { false }
        }
        XCTAssertEqual(recorder.state, .paused)
        browser.checkResult = true
        engine.resume()
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.state, .finished)
        XCTAssertEqual(recorder.resumes, 1)
        let log = try ActionLog.recoverJournal(from: recorder.folder.actionLogJournalURL)
        XCTAssertFalse(log.entries.contains { $0.stepID == "s1" })
    }

    func testManualResetAndStopRetainNoUnstartedSession() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL,
                         options: ReplayOptions(manualResetBeforeTake: true))
        try await waitFor { if case .userControl(let handover) = engine.state { handover.phase == .reset } else { false } }
        XCTAssertEqual(recorder.starts, 0)
        XCTAssertEqual(browser.controlChanges, [true])
        await engine.stop()
        XCTAssertEqual(engine.state, .stopped)
        XCTAssertFalse(engine.isRunning)
        XCTAssertEqual(recorder.completedCount, 0)
    }

    func testStopDuringLaunchCalibrationRehearsalAndTake() async throws {
        for phase in ["launch", "calibration", "rehearsal", "take"] {
            let (engine, browser, recorder, capture) = try fixture()
            defer { recorder.removeFiles() }
            if phase == "launch" { browser.blockLaunch = true }
            if phase == "calibration" { capture.block = true }
            browser.onPerform = { action, pacing in
                guard case .wait = action else { return }
                if (phase == "rehearsal" && pacing == .rehearsal) || (phase == "take" && pacing != .rehearsal) {
                    try await Task.sleep(for: .seconds(60))
                }
            }
            try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
            try await waitFor {
                switch (phase, engine.state) {
                case ("launch", .launching): browser.launchCount > 0
                case ("calibration", .calibrating): capture.calls > 0
                case ("rehearsal", .rehearsing): true
                case ("take", .recording): true
                default: false
                }
            }
            await engine.stop()
            XCTAssertEqual(engine.state, .stopped, phase)
            XCTAssertEqual(recorder.state, .idle, phase)
            if phase == "take" {
                XCTAssertEqual(RecordingManifest.load(from: recorder.folder.manifestURL)?.browserTake?.status, .stopped)
                XCTAssertTrue(FileManager.default.fileExists(atPath: recorder.folder.actionLogURL.path))
            }
        }
    }

    func testImmediateStopDoesNotLaunchLater() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
        await engine.stop()
        XCTAssertEqual(engine.state, .stopped)
        XCTAssertEqual(browser.launchCount, 0)
        XCTAssertEqual(recorder.starts, 0)
        engine.resume()
        await engine.stop()
        XCTAssertEqual(engine.state, .stopped)
    }

    func testStopDuringPausedCredentialHandoverKeepsPartialTake() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        let input = spec([.wait(seconds: 0), .handover(reason: .login, doneWhen: nil), .wait(seconds: 0)])
        try engine.start(spec: input, profileDirectory: recorder.folder.rootURL)
        try await waitFor { if case .userControl = engine.state { true } else { false } }
        engine.resume()
        try await waitFor {
            if case .userControl(let handover) = engine.state { handover.phase == .take } else { false }
        }
        XCTAssertEqual(recorder.state, .paused)
        let actionsBeforeStop = browser.actions.count
        await engine.stop()
        engine.resume()
        XCTAssertEqual(engine.state, .stopped)
        XCTAssertEqual(browser.actions.count, actionsBeforeStop)
        XCTAssertEqual(recorder.resumes, 0)
        XCTAssertEqual(recorder.completedCount, 1)
        XCTAssertEqual(RecordingManifest.load(from: recorder.folder.manifestURL)?.browserTake?.status, .stopped)
    }

    func testCleanupNeverStopsAnUnrelatedRecordingOnSharedController() async throws {
        let (engine, _, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        let input = spec([.wait(seconds: 0), .handover(reason: .manual, doneWhen: nil)])
        try engine.start(spec: input, profileDirectory: recorder.folder.rootURL)
        try await waitFor { if case .userControl = engine.state { true } else { false } }
        engine.resume()
        try await waitFor {
            if case .userControl(let handover) = engine.state { handover.phase == .take } else { false }
        }
        // Ordinary App controls ended the browser take and began another session.
        recorder.currentSessionFolder = SessionFolder.make(date: Date(), suffix: "unrelated", baseDirectory: recorder.folder.rootURL)
        recorder.state = .recording
        await engine.stop()
        XCTAssertEqual(recorder.state, .recording)
        XCTAssertEqual(recorder.completedCount, 0)
    }

    func testRetakeStillReceivesSafetyEventsOnSharedHost() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.state, .finished)
        browser.onPerform = { _, pacing in
            if pacing != .rehearsal {
                browser.emit(.viewportResized(CGSize(width: 10, height: 10)))
                try await Task.sleep(for: .seconds(60))
            }
        }
        try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.state, .failed(reason: "viewportResized"))
        XCTAssertEqual(recorder.completedCount, 2)
    }

    func testBlankLaunchCalibratesThenGrantsControlBeforeLeadingLoginNavigation() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        let input = spec([.handover(reason: .login, doneWhen: Expectation(url: "/ready")), .wait(seconds: 0)])
        try engine.start(spec: input, profileDirectory: recorder.folder.rootURL,
                         options: ReplayOptions(forceLoginHandover: true))
        try await waitFor { browser.handoverNavigations.count == 1 }
        XCTAssertEqual(Array(browser.trace.prefix(4)), ["launchBlank", "calibration", "grantControl", "handoverNavigation"])
        XCTAssertTrue(browser.actions.isEmpty)
        XCTAssertEqual(recorder.starts, 0)
        XCTAssertTrue(browser.userControl)
        // Force means offering control on startURL, not signing out or typing credentials.
        engine.resume()
        try await waitFor { browser.handoverNavigations.count == 2 }
        XCTAssertEqual(browser.handoverNavigations, [url, url])
        XCTAssertEqual(browser.actions.count, 1) // rehearsal wait only; no ordinary goto
        engine.resume()
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.state, .finished)
    }

    func testNotReadyResumeKeepsUserControlAndAllowsExplicitRetry() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        let input = spec([.wait(seconds: 0), .handover(reason: .login, doneWhen: nil), .wait(seconds: 0)])
        try engine.start(spec: input, profileDirectory: recorder.folder.rootURL)
        try await waitFor { if case .userControl = engine.state { true } else { false } }
        engine.resume()
        try await waitFor {
            if case .userControl(let handover) = engine.state { handover.phase == .take } else { false }
        }
        browser.notReadyCount = 1
        engine.resume()
        try await waitFor {
            if case .userControl(let handover) = engine.state { handover.expectationNotMet } else { false }
        }
        XCTAssertTrue(browser.userControl)
        XCTAssertEqual(recorder.state, .paused)
        XCTAssertEqual(recorder.resumes, 0)
        let commandCount = browser.commandCount
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertEqual(browser.commandCount, commandCount)
        engine.resume()
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.state, .finished)
        XCTAssertEqual(recorder.resumes, 1)
    }

    func testLeadingLoginExternalRedirectStaysInHandoverUntilManualRetry() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        browser.notReadyCount = 1
        let input = spec([.handover(reason: .login, doneWhen: Expectation(url: "/ready")), .wait(seconds: 0)])
        try engine.start(spec: input, profileDirectory: recorder.folder.rootURL)
        try await waitFor { browser.controlChanges == [true, false] }
        XCTAssertTrue(browser.userControl)
        XCTAssertTrue(browser.actions.isEmpty)
        XCTAssertEqual(browser.handoverNavigations, [url])
        let commandCount = browser.commandCount
        try await Task.sleep(for: .milliseconds(80))
        XCTAssertEqual(browser.commandCount, commandCount)
        engine.resume()
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.state, .finished)
        XCTAssertEqual(recorder.starts, 1)
        XCTAssertEqual(browser.handoverNavigations, [url, url])
    }

    func testRecorderLossClosesHostDuringAwaitedActionAndExpectation() async throws {
        for command in ["action", "expectation"] {
            let (engine, browser, recorder, _) = try fixture()
            defer { recorder.removeFiles() }
            let loseRecorder: () async throws -> Void = {
                // Deliberately ignores task cancellation: only immediate host close releases it.
                try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                    browser.onClose = { continuation.resume(throwing: BrowserHostError.terminated) }
                    recorder.state = .idle
                    recorder.currentSessionFolder = nil
                }
            }
            if command == "action" {
                browser.onPerform = { _, pacing in
                    if pacing != .rehearsal { try await loseRecorder() }
                }
            } else {
                browser.onCheck = { if recorder.starts > 0 { try await loseRecorder() } }
            }
            var input = spec()
            if command == "expectation" { input.steps[0].expect = Expectation(url: "/ready") }
            try engine.start(spec: input, profileDirectory: recorder.folder.rootURL)
            try await waitFor { if case .failed = engine.state { true } else { false } }
            XCTAssertEqual(engine.state, .failed(reason: "recordingInterrupted"), command)
            XCTAssertGreaterThan(browser.closeCount, 0)
            XCTAssertEqual(RecordingManifest.load(from: recorder.folder.manifestURL)?.browserTake?.status, .failed)
        }
    }

    func testLostOwnerDuringPausedHandoverFailsWithoutResumeOrStoppingNewSession() async throws {
        let (engine, browser, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        let input = spec([.wait(seconds: 0), .handover(reason: .manual, doneWhen: nil)])
        try engine.start(spec: input, profileDirectory: recorder.folder.rootURL)
        try await waitFor { if case .userControl = engine.state { true } else { false } }
        engine.resume()
        try await waitFor {
            if case .userControl(let handover) = engine.state { handover.phase == .take } else { false }
        }
        // An expected pause is healthy and must not close the host.
        try await Task.sleep(for: .milliseconds(80))
        XCTAssertEqual(recorder.state, .paused)
        XCTAssertEqual(browser.closeCount, 0)
        recorder.currentSessionFolder = SessionFolder.make(date: Date(), suffix: "new-session", baseDirectory: recorder.folder.rootURL)
        recorder.state = .recording
        try await waitFor { if case .failed = engine.state { true } else { false } }
        XCTAssertEqual(engine.state, .failed(reason: "recordingInterrupted"))
        XCTAssertEqual(recorder.state, .recording)
        XCTAssertEqual(recorder.resumes, 0)
        XCTAssertGreaterThan(browser.closeCount, 0)
    }

    func testCalibrationRetriesFreshAttemptsUntilMarkersPaint() async throws {
        var attempts = 0
        let origin = ContinuousClock.now
        var elapsed: Duration = .zero
        let viewport = try await ChromeReplayCapture.calibrateWhenPainted(
            now: { origin.advanced(by: elapsed) },
            sleep: { elapsed += $0 }
        ) {
            attempts += 1
            if attempts < 3 { throw ViewportCalibrator.CalibrationError.markersNotFound }
            return FakeReplayCapture.viewport
        }
        XCTAssertEqual(attempts, 3)
        XCTAssertEqual(elapsed, .milliseconds(200))
        XCTAssertEqual(viewport, FakeReplayCapture.viewport)
    }

    func testCalibrationRetryHasDeadlineAndDoesNotRetryOtherFailures() async throws {
        let origin = ContinuousClock.now
        var elapsed: Duration = .zero
        var attemptTimes: [Duration] = []
        var sleeps: [Duration] = []
        let now = { origin.advanced(by: elapsed) }
        let sleep: (Duration) async throws -> Void = { duration in
            sleeps.append(duration)
            elapsed += duration
        }
        do {
            _ = try await ChromeReplayCapture.calibrateWhenPainted(
                timeout: .milliseconds(25), retryDelay: .milliseconds(10), now: now, sleep: sleep
            ) {
                attemptTimes.append(elapsed)
                throw ViewportCalibrator.CalibrationError.markersNotFound
            }
            XCTFail("Missing markers must time out")
        } catch {
            XCTAssertEqual(error as? ViewportCalibrator.CalibrationError, .markersNotFound)
        }
        XCTAssertEqual(attemptTimes, [.zero, .milliseconds(10), .milliseconds(20)])
        XCTAssertEqual(sleeps, [.milliseconds(10), .milliseconds(10), .milliseconds(5)])
        XCTAssertEqual(elapsed, .milliseconds(25))

        elapsed = .zero
        attemptTimes = []
        sleeps = []
        do {
            _ = try await ChromeReplayCapture.calibrateWhenPainted(now: now, sleep: sleep) {
                attemptTimes.append(elapsed)
                throw ViewportCalibrator.CalibrationError.inconsistentGeometry
            }
            XCTFail("Invalid geometry is not a paint race")
        } catch {
            XCTAssertEqual(error as? ViewportCalibrator.CalibrationError, .inconsistentGeometry)
        }
        XCTAssertEqual(attemptTimes, [.zero])
        XCTAssertTrue(sleeps.isEmpty)
        XCTAssertEqual(elapsed, .zero)
    }

    func testCalibrationAttemptCanExhaustDeadlineWithoutSleepingOrRetrying() async throws {
        let origin = ContinuousClock.now
        var elapsed: Duration = .zero
        var attempts = 0
        var sleeps = 0
        do {
            _ = try await ChromeReplayCapture.calibrateWhenPainted(
                timeout: .milliseconds(25),
                now: { origin.advanced(by: elapsed) },
                sleep: { _ in sleeps += 1 }
            ) {
                attempts += 1
                elapsed += .milliseconds(25)
                throw ViewportCalibrator.CalibrationError.markersNotFound
            }
            XCTFail("An attempt that reaches the deadline must not retry")
        } catch {
            XCTAssertEqual(error as? ViewportCalibrator.CalibrationError, .markersNotFound)
        }
        XCTAssertEqual(attempts, 1)
        XCTAssertEqual(sleeps, 0)
        XCTAssertEqual(elapsed, .milliseconds(25))
    }

    func testCalibrationRetrySleepIsCancellable() async throws {
        var attempts = 0
        let task = Task {
            try await ChromeReplayCapture.calibrateWhenPainted(retryDelay: .seconds(1)) {
                attempts += 1
                throw ViewportCalibrator.CalibrationError.markersNotFound
            }
        }
        try await waitFor { attempts == 1 }
        task.cancel()
        do {
            _ = try await task.value
            XCTFail("Calibration must cancel during retry sleep")
        } catch { XCTAssertTrue(error is CancellationError) }
        XCTAssertEqual(attempts, 1)
    }

    func testResizeRefusalAndClosedFailWithFinalizedPartialSession() async throws {
        let events: [BrowserEvent] = [.viewportResized(CGSize(width: 900, height: 600)),
                                     .navigationRefused(URL(string: "https://refused.example")!), .closed(reason: "private host detail")]
        for event in events {
            let (engine, browser, recorder, _) = try fixture()
            defer { recorder.removeFiles() }
            browser.onPerform = { _, pacing in
                if pacing != .rehearsal {
                    browser.emit(event)
                    try await Task.sleep(for: .seconds(60))
                }
            }
            try engine.start(spec: spec(), profileDirectory: recorder.folder.rootURL)
            await engine.waitUntilFinished()
            guard case .failed = engine.state else { return XCTFail("Safety event must fail replay") }
            XCTAssertEqual(RecordingManifest.load(from: recorder.folder.manifestURL)?.browserTake?.status, .failed)
            XCTAssertEqual(recorder.completedCount, 1)
            XCTAssertTrue(FileManager.default.fileExists(atPath: recorder.folder.actionLogURL.path))
            XCTAssertFalse(engine.lastError?.contains("private host detail") ?? true)
        }
    }
}

@MainActor
private final class FakeReplayBrowser: BrowserDriving {
    nonisolated let events: AsyncStream<BrowserEvent>
    private let continuation: AsyncStream<BrowserEvent>.Continuation
    var actions: [(DemoAction, ActionPacing)] = []
    var controlChanges: [Bool] = []
    var handoverNavigations: [URL] = []
    var trace: [String] = []
    var userControl = false
    var notReadyCount = 0
    var launchCount = 0
    var closeCount = 0
    var commandCount = 0
    var checkResult = true
    var blockLaunch = false
    var onPerform: ((DemoAction, ActionPacing) async throws -> Void)?
    var onCheck: (() async throws -> Void)?
    var onClose: (() -> Void)?
    init() {
        let stream = AsyncStream<BrowserEvent>.makeStream()
        events = stream.stream; continuation = stream.continuation
    }
    func emit(_ event: BrowserEvent) { continuation.yield(event) }
    func launch(_ configuration: BrowserLaunch) async throws -> BrowserSession {
        launchCount += 1; commandCount += 1; trace.append("launchBlank")
        if blockLaunch { try await Task.sleep(for: .seconds(60)) }
        return BrowserSession(chromeProcessID: 123)
    }
    func perform(_ action: DemoAction, pacing: ActionPacing) async throws -> ActionOutcome {
        commandCount += 1; actions.append((action, pacing))
        trace.append("perform")
        XCTAssertFalse(userControl, "Ordinary actions cannot run under user control")
        if case .handover = action { XCTFail("Handovers must never be performed by the host") }
        try await onPerform?(action, pacing)
        return ActionOutcome(viewport: FakeReplayCapture.viewport.viewport)
    }
    func check(_ expectation: Expectation, timeout: TimeInterval) async throws -> Bool {
        commandCount += 1
        XCTAssertFalse(userControl, "Do not inspect page content during handover")
        try await onCheck?()
        return checkResult
    }
    func setUserControl(_ enabled: Bool) async throws {
        commandCount += 1; controlChanges.append(enabled)
        trace.append(enabled ? "grantControl" : "returnControl")
        if !enabled && notReadyCount > 0 {
            notReadyCount -= 1
            throw BrowserHostError.refused("notReady")
        }
        userControl = enabled
    }
    func navigateForHandover(to url: URL) async throws {
        XCTAssertTrue(userControl)
        commandCount += 1; handoverNavigations.append(url); trace.append("handoverNavigation")
    }
    func viewportMetrics() async throws -> BrowserViewportMetrics { FakeReplayCapture.viewport.viewport }
    func showCalibrationPage() async throws -> BrowserCalibration { throw BrowserHostError.unavailable }
    func snapshot() async throws -> String { XCTFail("Replay must not request page content"); return "" }
    func flushCapture() async throws -> [CapturedInteraction] {
        continuation.yield(.captureFlushed)
        return []
    }
    func close() async {
        closeCount += 1
        let completion = onClose; onClose = nil; completion?()
    }
}

@MainActor
private final class FakeReplayCapture: ReplayCapturePreparing {
    static let viewport = BrowserViewportMetadata(viewportRect: CGRect(x: 0, y: 80, width: 1200, height: 720),
        viewport: BrowserViewportMetrics(width: 1200, height: 720, devicePixelRatio: 1),
        frameSize: CGSize(width: 1200, height: 800), pixelsPerCSSPixel: 1)
    var calls = 0
    var block = false
    var failure: (any Error)?
    func prepare(browser: any BrowserDriving, session: BrowserSession, window: WindowSize) async throws -> ReplayCapture {
        calls += 1
        (browser as? FakeReplayBrowser)?.trace.append("calibration")
        if block { try await Task.sleep(for: .seconds(60)) }
        if let failure { throw failure }
        return ReplayCapture(request: RecordingRequest(profile: RecordingProfile(tracks: [.screen])), viewport: Self.viewport)
    }
}

@MainActor
private final class FakeReplayRecorder: BrowserTakeRecording {
    let folder: SessionFolder
    var state: RecordingState = .idle
    var currentSessionFolder: SessionFolder?
    var time: TimeInterval = 0
    var starts = 0
    var pauses = 0
    var resumes = 0
    var completedCount = 0
    var markers: [String] = []
    var request: RecordingRequest?
    var expectsWindowClose = false
    var onPause: (() -> Void)?
    var onFinalize: (() async throws -> Void)?
    var onCompleted: (() -> Void)?
    init() throws {
        folder = SessionFolder.make(date: Date(), suffix: UUID().uuidString,
            baseDirectory: FileManager.default.temporaryDirectory.appendingPathComponent("aura-replay-tests"))
        try FileManager.default.createDirectory(at: folder.rootURL, withIntermediateDirectories: true)
    }
    func removeFiles() { try? FileManager.default.removeItem(at: folder.rootURL) }
    func startBrowserTake(_ request: RecordingRequest, spec: DemoSpec, viewport: BrowserViewportMetadata) async throws -> SessionFolder {
        starts += 1; state = .recording; self.request = request; time = 0
        currentSessionFolder = folder
        expectsWindowClose = false
        try JSONEncoder().encode(spec).write(to: folder.demoSpecURL, options: .atomic)
        try JSONEncoder().encode(viewport).write(to: folder.viewportURL, options: .atomic)
        try Data().write(to: folder.actionLogJournalURL, options: .atomic)
        try RecordingManifest(profile: request.profile, startedAt: Date(), browserTake: request.browserTake).write(to: folder.manifestURL)
        return folder
    }
    func currentSessionTime() -> TimeInterval? { state == .recording || state == .paused ? time : nil }
    func browserStep(label: String) { markers.append(label) }
    func pause() { pauses += 1; state = .paused; onPause?() }
    func resume() { resumes += 1; state = .recording }
    func prepareToStopBrowserTake(sessionID: String) {
        guard currentSessionFolder?.id == sessionID, state == .recording || state == .paused else { return }
        expectsWindowClose = true
        if state == .recording { pause() }
    }
    func windowClosed() {
        guard state == .recording || state == .paused, !expectsWindowClose else { return }
        var manifest = RecordingManifest.load(from: folder.manifestURL)!
        manifest.browserTake?.status = .failed
        manifest.browserTake?.failureReason = "captureFailed"
        try? manifest.write(to: folder.manifestURL)
    }
    func stopBrowserTake(sessionID: String, status: BrowserTakeMetadata.Status, failureReason: String?) async throws {
        guard state != .idle, currentSessionFolder?.id == sessionID else { return }
        state = .stopping
        defer { state = .idle; currentSessionFolder = nil }
        try await onFinalize?()
        try ActionLog.finalizeJournal(in: folder)
        var manifest = RecordingManifest.load(from: folder.manifestURL)!
        if manifest.browserTake?.status != .failed {
            manifest.browserTake?.status = status; manifest.browserTake?.failureReason = failureReason
        }
        try manifest.write(to: folder.manifestURL)
        state = .idle; currentSessionFolder = nil; completedCount += 1
        onCompleted?()
    }
}

// MARK: - Narration

@MainActor
extension ReplayEngineTests {
    private func clip(_ seconds: TimeInterval, text: String, directory: URL) throws -> NarrationClip {
        let url = directory.appendingPathComponent(UUID().uuidString).appendingPathExtension("m4a")
        try TestMedia.writeSilentAudio(to: url, seconds: seconds)
        return NarrationClip(text: text, url: url, duration: seconds)
    }

    func testNarratedTakeWaitsForEachLineAndRecordsWhereEachStarted() async throws {
        let (engine, _, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        let cache = FileManager.default.temporaryDirectory.appendingPathComponent("aura-narrated-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: cache, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: cache) }

        var demo = spec([.wait(seconds: 0), .wait(seconds: 0)])
        demo.intro = "Intro."
        demo.outro = "Outro."
        demo.steps[0].narration = "First."
        demo.steps[1].narration = "Second."
        let track = NarrationTrack(clips: [
            .intro: try clip(0.2, text: "Intro.", directory: cache),
            .step("s0"): try clip(0.3, text: "First.", directory: cache),
            .step("s1"): try clip(0.3, text: "Second.", directory: cache),
            .outro: try clip(0.2, text: "Outro.", directory: cache)
        ])
        let start = ContinuousClock.now
        try engine.start(spec: demo, profileDirectory: recorder.folder.rootURL, options: ReplayOptions(narration: track))
        await engine.waitUntilFinished()
        let elapsed = ContinuousClock.now - start

        XCTAssertEqual(engine.state, .finished)
        // Lines alone are 1.0s; the beats between them (edge holds, lead, gaps) make it much longer.
        XCTAssertGreaterThan(elapsed, .seconds(1.0 + NarrationTiming.edgeHold * 2))

        let lines = try JSONDecoder().decode([NarrationLine].self, from: Data(contentsOf: recorder.folder.narrationLinesURL))
        XCTAssertEqual(lines.map(\.text), ["Intro.", "First.", "Second.", "Outro."])
        XCTAssertEqual(lines.map(\.stepID), [nil, "s0", "s1", nil])
        XCTAssertEqual(lines.map(\.duration), [0.2, 0.3, 0.3, 0.2])
        for line in lines {
            XCTAssertTrue(FileManager.default.fileExists(atPath: recorder.folder.narrationClipURL(for: line.id).path),
                          "each clip sits beside the session, named by its line")
        }
    }

    func testATakeWithNoNarrationIsUnchanged() async throws {
        let (engine, _, recorder, _) = try fixture()
        defer { recorder.removeFiles() }
        let start = ContinuousClock.now
        try engine.start(spec: spec([.wait(seconds: 0)]), profileDirectory: recorder.folder.rootURL)
        await engine.waitUntilFinished()
        XCTAssertEqual(engine.state, .finished)
        XCTAssertLessThan(ContinuousClock.now - start, .seconds(NarrationTiming.edgeHold), "no beats are added")
        XCTAssertFalse(FileManager.default.fileExists(atPath: recorder.folder.narrationLinesURL.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: recorder.folder.narrationURL.path))
    }
}
