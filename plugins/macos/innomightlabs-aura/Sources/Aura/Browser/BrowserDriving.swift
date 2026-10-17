import Foundation
import CoreGraphics

/// ReplayEngine owns rehearsal, recording state and handover; this boundary only drives Chrome.
protocol BrowserDriving: Sendable {
    func launch(_ configuration: BrowserLaunch) async throws -> BrowserSession
    func perform(_ action: DemoAction, pacing: ActionPacing) async throws -> ActionOutcome
    func check(_ expectation: Expectation, timeout: TimeInterval) async throws -> Bool
    func setUserControl(_ enabled: Bool) async throws
    /// Starts sign-in from an allowlisted URL only while the user owns control; redirects may reach an IdP.
    func navigateForHandover(to url: URL) async throws
    func viewportMetrics() async throws -> BrowserViewportMetrics
    func showCalibrationPage() async throws -> BrowserCalibration
    /// A value-free semantic inventory. Unavailable during user control.
    func snapshot() async throws -> String
    /// Stops capture delivery and returns pending interactions exactly once. Before returning, yield
    /// `captureFlushed` after all earlier events so the recorder can drain its stream in order.
    func flushCapture() async throws -> [CapturedInteraction]
    func close() async
    var events: AsyncStream<BrowserEvent> { get }
}

struct BrowserLaunch: Codable, Equatable, Sendable {
    var profileDirectory: URL
    var startURL: URL
    var window: WindowSize
    var allowedOrigins: [String]
    /// Record a demonstration: the user drives Chrome for the whole session and the host reports
    /// what they do. No action can be performed by Aura while this is on.
    var capture = false
}

struct BrowserSession: Codable, Equatable, Sendable {
    let chromeProcessID: Int32
}

struct ActionPacing: Codable, Equatable, Sendable {
    var moveSeconds: TimeInterval = 0.6
    var steps: Int = 24
    var typeDelayMs: Int = 45
    static let rehearsal = ActionPacing(moveSeconds: 0, steps: 1, typeDelayMs: 0)
}

struct BrowserViewportMetrics: Codable, Equatable, Sendable {
    var width: Double
    var height: Double
    var devicePixelRatio: Double
}

struct BrowserCalibrationMarker: Codable, Equatable, Sendable {
    var rect: BrowserRect
    /// RGB bytes, in top-left, top-right, bottom-left, bottom-right order.
    var color: [UInt8]
}

struct BrowserCalibration: Codable, Equatable, Sendable {
    var viewport: BrowserViewportMetrics
    var background: [UInt8]
    var markers: [BrowserCalibrationMarker]
}

struct ActionOutcome: Codable, Equatable, Sendable {
    var rect: BrowserRect? = nil
    var matched: String? = nil
    var viewport: BrowserViewportMetrics
}

/// One thing the user did while a demonstration was recorded, as the page described it. The host has
/// already refused credentials; `sensitiveInput` only says that the user went to enter one.
enum CapturedInteraction: Equatable, Sendable {
    case click(ElementTarget, rect: BrowserRect)
    case input(ElementTarget, value: String)
    case press(key: String)
    case scroll(ScrollPosition)
    case sensitiveInput
}

enum BrowserEvent: Equatable, Sendable {
    case captureFlushed
    case interaction(CapturedInteraction)
    case mouseMoved(to: CGPoint)
    case mouseDown(at: CGPoint)
    case mouseUp(at: CGPoint)
    /// `clean` is whether the address had no query or fragment, which is when a path alone can be
    /// expected on replay.
    case navigated(URL, clean: Bool)
    case navigationRefused(URL)
    case viewportResized(CGSize)
    case closed(reason: String)
}

enum BrowserHostError: Error, LocalizedError, Equatable {
    case unavailable, notRunning, busy, timedOut, terminated, invalidResponse
    case refused(String)

    var errorDescription: String? {
        switch self {
        case .unavailable: "The browser engine could not start. Check the installed Node engine and Chrome."
        case .notRunning: "The browser host is not running."
        case .busy: "The browser host is busy."
        case .timedOut: "The browser command timed out; the browser was closed."
        case .terminated: "The browser host stopped."
        case .invalidResponse: "The browser host returned an invalid response."
        case .refused(let code): "The browser refused the command (\(code))."
        }
    }
}
