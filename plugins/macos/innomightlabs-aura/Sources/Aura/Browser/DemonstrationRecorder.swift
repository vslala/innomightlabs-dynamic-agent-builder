import Combine
import Foundation

enum DemonstrationError: Error, LocalizedError, Equatable {
    case busy
    case nothingRecorded
    case invalidStartURL

    var errorDescription: String? {
        switch self {
        case .busy: return "A demonstration is already being recorded."
        case .nothingRecorded: return "No steps were recorded. Click through the flow in Chrome, then finish."
        case .invalidStartURL: return "Enter the web address where the demo starts, for example https://app.example.com/."
        }
    }
}

/// Records a demonstration: Chrome opens on the start page, the user does the flow themselves, and
/// the steps appear as they go. Finishing, or closing Chrome, produces a spec.
///
/// Owns no recording hardware and performs no actions: `launch(capture: true)` makes the host hold
/// the browser with the user throughout.
@MainActor
final class DemonstrationRecorder: ObservableObject {
    enum State: Equatable {
        case idle, launching, recording, finishing
    }

    @Published private(set) var state: State = .idle
    @Published private(set) var steps: [DemoStep] = []
    @Published private(set) var lastError: String?

    private let browser: any BrowserDriving
    private var capture: DemonstrationCapture?
    private var pending: (title: String, startURL: URL, window: WindowSize)?
    private var eventTask: Task<Void, Never>?
    private var finished: CheckedContinuation<Void, Never>?
    private var captureFlushed = false
    private var flushWaiter: CheckedContinuation<Void, Never>?

    init(browser: any BrowserDriving) {
        self.browser = browser
    }

    var isRunning: Bool { state != .idle }

    /// Opens Chrome on `startURL`. Returns once the user can start; steps arrive in `steps`.
    func start(title: String, startURL: URL, profileDirectory: URL, window: WindowSize = WindowSize(width: 1440, height: 900)) async throws {
        guard state == .idle else { throw DemonstrationError.busy }
        guard let origin = try? DemoSpec.origin(of: startURL) else { throw DemonstrationError.invalidStartURL }
        state = .launching
        steps = []
        captureFlushed = false
        lastError = nil
        capture = DemonstrationCapture(allowedOrigins: [origin])
        pending = (title, startURL, window)

        eventTask = Task { [weak self, browser] in
            for await event in browser.events {
                guard !Task.isCancelled else { break }
                self?.receive(event)
            }
        }
        do {
            _ = try await browser.launch(BrowserLaunch(
                profileDirectory: profileDirectory, startURL: startURL, window: window,
                allowedOrigins: [origin], capture: true
            ))
            state = .recording
            try await browser.navigateForHandover(to: startURL)
        } catch {
            await tearDown()
            throw error
        }
    }

    /// Ends the demonstration and returns what was recorded. Closing Chrome does the same.
    func finish() async throws -> DemoSpec {
        guard capture != nil, let pending, state == .recording || state == .finishing else { throw DemonstrationError.nothingRecorded }
        state = .finishing
        let interactions: [CapturedInteraction]
        do { interactions = try await browser.flushCapture() }
        catch { await tearDown(); throw error }
        if !captureFlushed { await withCheckedContinuation { flushWaiter = $0 } }
        for interaction in interactions { capture?.receive(interaction) }
        let recorded = capture?.finish() ?? []
        await tearDown()
        guard !recorded.isEmpty else { throw DemonstrationError.nothingRecorded }
        return DemoSpec(
            title: pending.title, startURL: pending.startURL,
            allowedOrigins: try [DemoSpec.origin(of: pending.startURL)], window: pending.window, steps: recorded
        )
    }

    func cancel() async {
        await tearDown()
    }

    private func receive(_ event: BrowserEvent) {
        switch event {
        case .captureFlushed:
            captureFlushed = true
            flushWaiter?.resume()
            flushWaiter = nil
        case .interaction(let interaction):
            capture?.receive(interaction)
        case .navigated(let url, let clean):
            capture?.navigated(to: url, clean: clean)
        case .closed:
            // The user closed Chrome: that is how a demonstration ends.
            if state == .recording { state = .finishing }
            finished?.resume()
            finished = nil
        default: break
        }
        steps = capture?.steps ?? []
    }

    /// Resolves once the user has closed Chrome or `finish`/`cancel` ran, for a caller that wants to
    /// wait on the user ending it themselves.
    func waitUntilClosed() async {
        guard state == .recording else { return }
        await withCheckedContinuation { finished = $0 }
    }

    private func tearDown() async {
        await browser.close()
        flushWaiter?.resume()
        flushWaiter = nil
        eventTask?.cancel()
        eventTask = nil
        finished?.resume()
        finished = nil
        capture = nil
        pending = nil
        state = .idle
    }
}
