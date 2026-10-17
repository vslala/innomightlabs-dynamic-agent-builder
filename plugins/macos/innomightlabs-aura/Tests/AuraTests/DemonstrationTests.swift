import XCTest
@testable import Aura

final class DemonstrationCaptureTests: XCTestCase {
    private let app = URL(string: "https://app.example.com/dashboard")!
    private func target(_ name: String) -> ElementTarget {
        ElementTarget(candidates: [LocatorCandidate(role: "button", name: name), LocatorCandidate(css: "#\(name.lowercased())")])
    }
    private let rect = BrowserRect(x: 1, y: 2, width: 30, height: 10)

    private func capture() -> DemonstrationCapture {
        var capture = DemonstrationCapture(allowedOrigins: ["https://app.example.com"])
        capture.navigated(to: app, clean: true) // the start page, which Aura opens itself
        return capture
    }

    func testScrollsCoalesceOnlyForTheSameTargetIgnoringDisplayHints() {
        var c = capture()
        let a = target("First"), b = target("Second")
        c.receive(.scroll(.init(x: 0, y: 100, target: a)))
        var moved = a
        moved.hintRect = rect
        c.receive(.scroll(.init(x: 0, y: 200, target: moved)))
        c.receive(.scroll(.init(x: 0, y: 50, target: b)))
        c.receive(.scroll(.init(x: 0, y: 300)))
        c.receive(.scroll(.init(x: 0, y: 150, target: a)))
        XCTAssertEqual(c.steps.count, 4)
        XCTAssertEqual(c.steps.map(\.intent), ["Scroll down", "Scroll down", "Scroll down", "Scroll up"])
    }

    func testClicksBecomeNamedStepsInOrder() {
        var c = capture()
        c.receive(.click(target("Create"), rect: rect))
        c.receive(.click(target("Save"), rect: rect))
        XCTAssertEqual(c.steps.map(\.id), ["s1", "s2"])
        XCTAssertEqual(c.steps.map(\.intent), ["Click “Create”", "Click “Save”"])
        XCTAssertEqual(c.steps[0].action, .click(target("Create")))
        XCTAssertEqual(c.steps.map(\.emphasis), [.ripple, .ripple], "a click ripples unless the user turns it off")
    }

    func testChatMessagesRemainSeparateAcrossSubmitKeys() throws {
        var c = capture()
        let field = ElementTarget(candidates: [LocatorCandidate(role: "textbox", name: "Message")])
        let messages = ["Hello 👋\n世界", "  Second message\nwith paste  "]
        for message in messages {
            c.receive(.input(field, value: message))
            c.receive(.press(key: "Enter"))
        }
        XCTAssertEqual(c.finish().map(\.action), messages.flatMap {
            [.fill(field, value: .literal($0)), .press(key: "Enter")]
        })
        let spec = DemoSpec(title: "Conversation", startURL: app, allowedOrigins: ["https://app.example.com"],
                            window: WindowSize(width: 1440, height: 900), steps: c.finish())
        XCTAssertNoThrow(try spec.validate())
        let data = try JSONEncoder().encode(spec)
        XCTAssertEqual(try JSONDecoder().decode(DemoSpec.self, from: data), spec)
    }

    func testTypingIsOneStepWithTheFinalText() {
        var c = capture()
        let field = ElementTarget(candidates: [LocatorCandidate(role: "textbox", name: "Website")])
        c.receive(.input(field, value: "https://exam"))
        c.receive(.input(field, value: "https://example.com"))
        XCTAssertEqual(c.steps.count, 1)
        XCTAssertEqual(c.steps[0].action, .fill(field, value: .literal("https://example.com")))
        XCTAssertEqual(c.steps[0].intent, "Fill in “Website”", "the intent never echoes what was typed")

        c.receive(.input(ElementTarget(candidates: [LocatorCandidate(role: "textbox", name: "Name")]), value: "Ila"))
        XCTAssertEqual(c.steps.count, 2, "a different field is a different step")
    }

    func testANavigationAfterAnActionIsThatActionsResult() {
        var c = capture()
        c.receive(.click(target("Create"), rect: rect))
        c.navigated(to: URL(string: "https://app.example.com/old")!, clean: true)
        c.navigated(to: URL(string: "https://app.example.com/agents/new")!, clean: true)
        XCTAssertEqual(c.steps.count, 1, "no extra goto step")
        XCTAssertEqual(c.steps[0].expect, Expectation(url: "/agents/new"), "a redirect chain ends on the page the user saw")

        c.receive(.click(target("Next"), rect: rect))
        c.navigated(to: URL(string: "https://app.example.com/agents/new?step=2")!, clean: false)
        XCTAssertNil(c.steps[1].expect, "a page with a query cannot be matched by path alone, so nothing is promised")
    }

    func testTheStartPageIsNotAStepWhereverItLands() {
        var c = DemonstrationCapture(allowedOrigins: ["https://app.example.com"])
        c.navigated(to: URL(string: "https://app.example.com/login")!, clean: true)
        XCTAssertTrue(c.steps.isEmpty, "the start redirected to a sign-in page, which is still just the start")
        c.navigated(to: URL(string: "https://app.example.com/pricing")!, clean: true)
        c.navigated(to: app, clean: true)
        XCTAssertTrue(c.steps.isEmpty, "the whole automatic initial redirect chain is part of opening the start page")
        c.receive(.click(target("Create"), rect: rect))
        XCTAssertEqual(c.steps.map(\.action), [.click(target("Create"))])
    }

    func testSigningInIsAHandoverAndNothingInsideItIsRecorded() throws {
        var c = capture()
        c.receive(.click(target("Sign in"), rect: rect))
        c.navigated(to: URL(string: "https://app.example.com/login")!, clean: true)
        c.receive(.sensitiveInput)
        c.receive(.input(ElementTarget(candidates: [LocatorCandidate(role: "textbox", name: "Anything")]), value: "typed while signing in"))
        c.receive(.click(target("Log in"), rect: rect))
        c.receive(.sensitiveInput)
        XCTAssertEqual(c.steps.count, 1, "the click that opened login belongs to the handover")
        XCTAssertEqual(c.steps[0].action, .handover(reason: .login, doneWhen: nil))

        c.navigated(to: URL(string: "https://app.example.com/home")!, clean: true)
        XCTAssertEqual(c.steps[0].action, .handover(reason: .login, doneWhen: Expectation(url: "/home")),
                       "replay resumes once the user has landed where they landed")

        c.receive(.click(target("Create"), rect: rect))
        XCTAssertEqual(c.steps.map(\.action), [
            .handover(reason: .login, doneWhen: Expectation(url: "/home")), .click(target("Create"))
        ], "the first post-login action is retained")
        let encoded = try String(data: JSONEncoder().encode(c.steps), encoding: .utf8) ?? ""
        XCTAssertFalse(encoded.contains("typed while signing in"))
    }

    func testLeavingForAnotherOriginIsAHandoverToo() {
        var c = capture()
        c.receive(.click(target("Continue with Google"), rect: rect))
        c.navigated(to: URL(string: "https://accounts.google.com/signin")!, clean: true)
        XCTAssertEqual(c.steps.count, 1, "grant user control before the initiating Google click")
        guard case .handover = c.steps[0].action else { return XCTFail("Expected a handover") }
        c.receive(.click(target("Next"), rect: rect))
        XCTAssertEqual(c.steps.count, 1, "nothing on the identity provider's page is a step")
        c.navigated(to: URL(string: "https://app.example.com/dashboard")!, clean: true)
        XCTAssertEqual(c.steps[0].action, .handover(reason: .login, doneWhen: Expectation(url: "/dashboard")))
    }

    func testInitialRedirectsAndRepeatedCredentialTouchesMakeOneFinalDashboardHandover() throws {
        var c = DemonstrationCapture(allowedOrigins: ["https://app.example.com"])
        let login = URL(string: "https://app.example.com/login")!
        c.navigated(to: URL(string: "https://app.example.com/")!, clean: true)
        c.navigated(to: login, clean: true)
        c.receive(.sensitiveInput)
        c.receive(.click(target("Log in"), rect: rect))
        c.navigated(to: login, clean: true)
        c.receive(.sensitiveInput)
        c.receive(.input(target("Password"), value: "must never be saved"))
        c.receive(.press(key: "Enter"))
        c.navigated(to: app, clean: true)
        c.navigated(to: app, clean: true)
        XCTAssertEqual(c.finish().map(\.action), [
            .handover(reason: .login, doneWhen: Expectation(url: "/dashboard"))
        ], "no initial goto, intermediary login checkpoint, or redundant dashboard goto")

        let create = target("Create")
        let settings = target("Settings")
        let field = ElementTarget(candidates: [LocatorCandidate(role: "textbox", name: "Website")])
        c.receive(.click(create, rect: rect))
        c.receive(.click(settings, rect: rect))
        c.receive(.input(field, value: "https://example.com"))
        XCTAssertEqual(c.finish().map(\.action), [
            .handover(reason: .login, doneWhen: Expectation(url: "/dashboard")),
            .click(create), .click(settings), .fill(field, value: .literal("https://example.com"))
        ])
        XCTAssertEqual(c.steps.map(\.id), ["s1", "s2", "s3", "s4"])
        let spec = DemoSpec(title: "Captured login", startURL: login, allowedOrigins: ["https://app.example.com"],
                            window: WindowSize(width: 1440, height: 900), steps: c.finish())
        XCTAssertNoThrow(try spec.validate())
        let data = try JSONEncoder().encode(spec)
        XCTAssertEqual(try JSONDecoder().decode(DemoSpec.self, from: data), spec)
        XCTAssertFalse(String(decoding: data, as: UTF8.self).contains("must never be saved"))
    }

    func testLoginRedirectsStayOpenUntilTheFirstPostLoginInteraction() {
        var c = capture()
        c.receive(.sensitiveInput)
        c.navigated(to: URL(string: "https://app.example.com/login")!, clean: true)
        c.navigated(to: URL(string: "https://app.example.com/auth/callback")!, clean: true)
        c.navigated(to: app, clean: true)
        c.receive(.click(target("Create"), rect: rect))
        c.navigated(to: URL(string: "https://app.example.com/agents/new")!, clean: true)
        XCTAssertEqual(c.steps.map(\.action), [
            .handover(reason: .login, doneWhen: Expectation(url: "/dashboard")), .click(target("Create"))
        ])
        XCTAssertEqual(c.steps[1].expect, Expectation(url: "/agents/new"))
    }

    func testExternalAuthFoldsOnlyItsInitiatingClickAndPreservesEarlierSteps() {
        var c = capture()
        c.receive(.click(target("Settings"), rect: rect))
        c.navigated(to: URL(string: "https://app.example.com/settings")!, clean: true)
        c.receive(.click(target("Continue with Google"), rect: rect))
        c.navigated(to: URL(string: "https://accounts.google.com/signin")!, clean: true)
        c.navigated(to: URL(string: "https://accounts.google.com/consent")!, clean: true)
        c.receive(.sensitiveInput)
        c.receive(.click(target("Allow"), rect: rect))
        c.navigated(to: app, clean: true)
        c.receive(.click(target("Create"), rect: rect))
        XCTAssertEqual(c.steps.map(\.action), [
            .click(target("Settings")),
            .handover(reason: .login, doneWhen: Expectation(url: "/dashboard")), .click(target("Create"))
        ])
        XCTAssertEqual(c.steps[0].expect, Expectation(url: "/settings"))
        XCTAssertEqual(c.steps.map(\.id), ["s1", "s2", "s3"])
    }

    func testAnIntermediateLoginPageAndGoogleClickReuseTheSameHandover() {
        var c = capture()
        c.receive(.sensitiveInput)
        c.navigated(to: URL(string: "https://app.example.com/login")!, clean: true)
        c.receive(.click(target("Continue with Google"), rect: rect))
        c.navigated(to: URL(string: "https://accounts.google.com/signin")!, clean: true)
        c.navigated(to: app, clean: true)
        XCTAssertEqual(c.finish().map(\.action), [
            .handover(reason: .login, doneWhen: Expectation(url: "/dashboard"))
        ], "an intermediary login checkpoint must not survive the external sign-in")
    }

    func testANewCredentialTouchClearsAnIntermediateCompletionUntilAnotherNavigation() {
        var c = capture()
        c.receive(.sensitiveInput)
        c.navigated(to: URL(string: "https://app.example.com/login")!, clean: true)
        c.receive(.sensitiveInput)
        c.receive(.click(target("Log in"), rect: rect))
        c.receive(.press(key: "Enter"))
        XCTAssertEqual(c.finish().map(\.action), [.handover(reason: .login, doneWhen: nil)])
    }

    func testDirtyPostLoginDestinationUsesFirstClickedTargetAndRetainsTheClick() {
        var c = capture()
        c.receive(.sensitiveInput)
        c.navigated(to: app, clean: true)
        c.navigated(to: URL(string: "https://app.example.com/dashboard?tab=agents")!, clean: false)
        c.receive(.click(target("Create"), rect: rect))
        XCTAssertEqual(c.steps.map(\.action), [
            .handover(reason: .login, doneWhen: Expectation(visible: target("Create").candidates.first)),
            .click(target("Create"))
        ], "a dirty URL must not leave a stale path-only completion")
    }

    func testAnUnfinishedSignInIsLeftOpenForReplayToAskTheUser() {
        var c = capture()
        c.receive(.sensitiveInput)
        XCTAssertEqual(c.finish().map(\.action), [.handover(reason: .login, doneWhen: nil)])
    }

    func testKeysArePreservedAndScrollsAreTidied() {
        var c = capture()
        let keys = ["Tab", "Shift+Tab", "Enter", "Enter", "Escape", "Escape", "Meta+Enter"]
        for key in keys { c.receive(.press(key: key)) }
        XCTAssertEqual(c.steps.map(\.action), keys.map { .press(key: $0) })
        c.receive(.scroll(ScrollPosition(x: 0, y: 200)))
        c.receive(.scroll(ScrollPosition(x: 0, y: 640)))
        XCTAssertEqual(c.steps.count, keys.count + 1, "a scroll is one step, ending where the user stopped")
        XCTAssertEqual(c.steps.last?.action, .scroll(to: ScrollPosition(x: 0, y: 640)))
        XCTAssertEqual(c.steps.last?.intent, "Scroll down")
        c.receive(.click(target("Top"), rect: rect))
        c.receive(.scroll(ScrollPosition(x: 0, y: 0)))
        XCTAssertEqual(c.steps.last?.intent, "Scroll up")
    }

    func testWhatIsCapturedIsAValidSpecThatReplayAccepts() throws {
        var c = capture()
        c.receive(.click(target("Create"), rect: rect))
        c.navigated(to: URL(string: "https://app.example.com/agents/new")!, clean: true)
        c.receive(.input(ElementTarget(candidates: [LocatorCandidate(role: "textbox", name: "Website")], hintRect: rect), value: "https://example.com"))
        c.receive(.press(key: "Enter"))
        c.receive(.sensitiveInput)
        c.navigated(to: URL(string: "https://app.example.com/home")!, clean: true)
        let spec = DemoSpec(title: "Demo", startURL: app, allowedOrigins: ["https://app.example.com"],
                            window: WindowSize(width: 1440, height: 900), steps: c.finish())
        XCTAssertNoThrow(try spec.validate())
        let data = try JSONEncoder().encode(spec)
        XCTAssertEqual(try JSONDecoder().decode(DemoSpec.self, from: data), spec)
    }
}

@MainActor
final class DemonstrationRecorderTests: XCTestCase {
    private let start = URL(string: "https://app.example.com/dashboard")!
    private let profile = FileManager.default.temporaryDirectory.appendingPathComponent("aura-demonstration-profile")
    private func target(_ name: String) -> ElementTarget { ElementTarget(candidates: [LocatorCandidate(role: "button", name: name)]) }

    private func waitFor(_ predicate: () -> Bool) async throws {
        for _ in 0..<500 {
            if predicate() { return }
            try await Task.sleep(for: .milliseconds(2))
        }
        XCTFail("Condition was not reached")
    }

    func testImmediateFinishDrainsEarlierEventsThenAppendsPendingScrollExactlyOnce() async throws {
        let browser = RecordingBrowser()
        let recorder = DemonstrationRecorder(browser: browser)
        try await recorder.start(title: "Demo", startURL: start, profileDirectory: profile)
        let scroll = ScrollPosition(x: 0, y: 240, target: target("Panel"))
        browser.emit(.interaction(.click(target("Create"), rect: .init(x: 0, y: 0, width: 10, height: 10))))
        browser.pendingInteractions = [.scroll(scroll)]
        let spec = try await recorder.finish()
        XCTAssertEqual(spec.steps.map(\.action), [.click(target("Create")), .scroll(to: scroll)])
    }

    func testRecordsWhatTheUserDoesAndReturnsASpec() async throws {
        let browser = RecordingBrowser()
        let recorder = DemonstrationRecorder(browser: browser)
        try await recorder.start(title: "Build a chatbot", startURL: start, profileDirectory: profile)
        XCTAssertEqual(recorder.state, .recording)
        XCTAssertEqual(browser.launched?.capture, true, "the host is told to hold the browser with the user")
        XCTAssertEqual(browser.launched?.allowedOrigins, ["https://app.example.com"])
        XCTAssertEqual(browser.handoverNavigations, [start], "Chrome opens on the start page")

        browser.emit(.navigated(start, clean: true))
        browser.emit(.interaction(.click(target("Create"), rect: BrowserRect(x: 1, y: 1, width: 5, height: 5))))
        try await waitFor { recorder.steps.count == 1 }

        let spec = try await recorder.finish()
        XCTAssertEqual(spec.title, "Build a chatbot")
        XCTAssertEqual(spec.allowedOrigins, ["https://app.example.com"])
        XCTAssertEqual(spec.steps.map(\.intent), ["Click “Create”"])
        XCTAssertNoThrow(try spec.validate())
        XCTAssertEqual(recorder.state, .idle)
        XCTAssertEqual(browser.closeCount, 1)
    }

    func testClosingChromeEndsTheDemonstrationAndKeepsWhatWasDone() async throws {
        let browser = RecordingBrowser()
        let recorder = DemonstrationRecorder(browser: browser)
        try await recorder.start(title: "Demo", startURL: start, profileDirectory: profile)
        browser.emit(.navigated(start, clean: true))
        browser.emit(.interaction(.click(target("Create"), rect: BrowserRect(x: 1, y: 1, width: 5, height: 5))))
        browser.emit(.closed(reason: "Browser closed"))
        try await waitFor { recorder.state == .finishing }
        let spec = try await recorder.finish()
        XCTAssertEqual(spec.steps.count, 1)
    }

    func testAnEmptyDemonstrationIsAnErrorNotAnEmptySpec() async throws {
        let browser = RecordingBrowser()
        let recorder = DemonstrationRecorder(browser: browser)
        try await recorder.start(title: "Demo", startURL: start, profileDirectory: profile)
        do { _ = try await recorder.finish(); XCTFail("Expected an error") }
        catch { XCTAssertEqual(error as? DemonstrationError, .nothingRecorded) }
        XCTAssertEqual(recorder.state, .idle)
        XCTAssertEqual(browser.closeCount, 1, "Chrome is closed either way")
    }

    func testOnlyOneAtATimeAndABadStartURLIsRefused() async throws {
        let browser = RecordingBrowser()
        let recorder = DemonstrationRecorder(browser: browser)
        do { try await recorder.start(title: "x", startURL: URL(string: "ftp://example.com")!, profileDirectory: profile); XCTFail() }
        catch { XCTAssertEqual(error as? DemonstrationError, .invalidStartURL) }
        try await recorder.start(title: "x", startURL: start, profileDirectory: profile)
        do { try await recorder.start(title: "y", startURL: start, profileDirectory: profile); XCTFail() }
        catch { XCTAssertEqual(error as? DemonstrationError, .busy) }
        await recorder.cancel()
        XCTAssertEqual(recorder.state, .idle)
    }

    func testALaunchFailureLeavesNothingRunning() async throws {
        let browser = RecordingBrowser()
        browser.launchError = BrowserHostError.unavailable
        let recorder = DemonstrationRecorder(browser: browser)
        do { try await recorder.start(title: "x", startURL: start, profileDirectory: profile); XCTFail() }
        catch { XCTAssertEqual(error as? BrowserHostError, .unavailable) }
        XCTAssertEqual(recorder.state, .idle)
        XCTAssertEqual(browser.closeCount, 1)
    }
}

/// A browser that records how it was driven and lets a test play the user's part.
private final class RecordingBrowser: BrowserDriving, @unchecked Sendable {
    nonisolated let events: AsyncStream<BrowserEvent>
    private let continuation: AsyncStream<BrowserEvent>.Continuation
    private(set) var launched: BrowserLaunch?
    private(set) var handoverNavigations: [URL] = []
    private(set) var closeCount = 0
    var launchError: Error?
    var pendingInteractions: [CapturedInteraction] = []

    init() {
        let stream = AsyncStream<BrowserEvent>.makeStream()
        events = stream.stream
        continuation = stream.continuation
    }

    func emit(_ event: BrowserEvent) { continuation.yield(event) }
    func launch(_ configuration: BrowserLaunch) async throws -> BrowserSession {
        if let launchError { throw launchError }
        launched = configuration
        return BrowserSession(chromeProcessID: 1)
    }
    func navigateForHandover(to url: URL) async throws { handoverNavigations.append(url) }
    func flushCapture() async throws -> [CapturedInteraction] {
        continuation.yield(.captureFlushed)
        let pending = pendingInteractions
        pendingInteractions = []
        return pending
    }
    func close() async { closeCount += 1 }
    func perform(_ action: DemoAction, pacing: ActionPacing) async throws -> ActionOutcome { XCTFail("A demonstration performs nothing"); throw BrowserHostError.refused("x") }
    func check(_ expectation: Expectation, timeout: TimeInterval) async throws -> Bool { XCTFail(); return false }
    func setUserControl(_ enabled: Bool) async throws { XCTFail("A demonstration never toggles control") }
    func viewportMetrics() async throws -> BrowserViewportMetrics { throw BrowserHostError.unavailable }
    func showCalibrationPage() async throws -> BrowserCalibration { throw BrowserHostError.unavailable }
    func snapshot() async throws -> String { XCTFail(); return "" }
}
